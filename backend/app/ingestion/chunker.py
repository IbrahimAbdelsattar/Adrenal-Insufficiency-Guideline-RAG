"""Chunking strategies (FR-011 through FR-014, FR-016, Day 2 Lab).

Supports two distinct chunking configurations for comparative empirical benchmarking:
- Config A (Fixed-size): Small fixed token windows (e.g. 256 tokens, 10% overlap)
- Config B (Section-aware): Atomic recommendation packing respecting guideline structure (600-800 tokens)

The load-bearing invariant of Config B: a numbered recommendation is atomic. Blocks are packed
toward the target size, but a recommendation is never divided — splitting one
mid-sentence yields a chunk that is incoherent and clinically partial. An oversized
recommendation is emitted whole and flagged rather than truncated.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

import tiktoken

from backend.app.config import Settings, get_settings
from backend.app.ingestion.sectioner import Block
from backend.app.models import Chunk, SourceDocument

_ENCODING_NAME = "cl100k_base"  # matches the embedding model family (research.md D6)

# NG243's "Rationale and impact" back-matter is full of bare pointers such as
# "Recommendations 1.2.1 to 1.2.4". They carry no clinical content, cannot be
# understood standalone (FR-013), and only dilute retrieval. Matched narrowly so
# genuine short glossary definitions survive.
_CROSS_REFERENCE = re.compile(
    r"^Recommendations?\s+[\d.]+(\s*(?:to|and|,)\s*[\d.]+)*\.?$",
    re.IGNORECASE,
)


def is_navigational(text: str) -> bool:
    """True for bare cross-reference pointers that carry no clinical content."""
    return bool(_CROSS_REFERENCE.match(text.strip()))


@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def _group_key(block: Block) -> tuple[str, str]:
    """Chunks never span a section or sub-section boundary in section-aware mode."""
    return (block.section_number, block.subsection_title)


def _build_chunk(
    group: list[Block],
    doc: SourceDocument,
    sequence: int,
    max_tokens: int,
    caution: bool,
) -> Chunk:
    text = "\n\n".join(block.text for block in group).strip()
    tokens = count_tokens(text)
    first = group[0]
    rec_ids = [b.recommendation_id for b in group if b.recommendation_id]

    return Chunk(
        chunk_id=f"{doc.doc_id}_p{first.page_number:02d}_c{sequence:02d}",
        text=text,
        document_name=doc.document_name,
        doc_id=doc.doc_id,
        source_url=doc.source_url,
        document_type=doc.document_type.value,
        publication_year=doc.publication_year,
        requires_caution=caution,
        page_number=first.page_number,
        section_title=first.section_title,
        section_number=first.section_number,
        subsection_title=first.subsection_title,
        recommendation_ids=",".join(rec_ids),
        token_count=tokens,
        is_oversized=tokens > max_tokens,
    )


def chunk_blocks_section(
    blocks: list[Block],
    doc: SourceDocument,
    settings: Settings | None = None,
) -> list[Chunk]:
    """Config B: Pack atomic blocks into section-aware chunks within the configured band."""
    settings = settings or get_settings()
    target = settings.chunk_target_tokens
    maximum = settings.chunk_max_tokens
    caution = doc.requires_caution()

    chunks: list[Chunk] = []
    sequence = 0
    pending: list[Block] = []
    pending_tokens = 0
    current_key: tuple[str, str] | None = None

    def flush() -> None:
        nonlocal pending, pending_tokens, sequence
        if not pending:
            return
        sequence += 1
        chunks.append(_build_chunk(pending, doc, sequence, maximum, caution))
        pending, pending_tokens = [], 0

    for block in blocks:
        # Drop navigational pointers before packing so they never reach the index.
        if not block.recommendation_id and is_navigational(block.text):
            continue

        block_tokens = count_tokens(block.text)
        key = _group_key(block)

        if current_key is not None and key != current_key:
            flush()
        current_key = key

        # A single block over the ceiling stands alone, whole and flagged.
        if block_tokens > maximum:
            flush()
            pending, pending_tokens = [block], block_tokens
            flush()
            continue

        # Adding this block would overshoot the target: close the current chunk first.
        if pending and pending_tokens + block_tokens > target:
            flush()

        pending.append(block)
        pending_tokens += block_tokens

    flush()
    return chunks


def chunk_blocks_fixed(
    blocks: list[Block],
    doc: SourceDocument,
    chunk_size: int = 256,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Config A: Fixed-size chunking (e.g. 256 tokens, 10% overlap)."""
    enc = _encoding()
    caution = doc.requires_caution()
    overlap_tokens = int(chunk_size * overlap_pct)
    step = max(1, chunk_size - overlap_tokens)

    # Collect cleaned textual blocks
    filtered_blocks = [
        b for b in blocks if b.recommendation_id or not is_navigational(b.text)
    ]
    if not filtered_blocks:
        return []

    full_text = "\n\n".join(b.text for b in filtered_blocks)
    tokens = enc.encode(full_text)

    chunks: list[Chunk] = []
    sequence = 0

    for start in range(0, len(tokens), step):
        chunk_token_ids = tokens[start : start + chunk_size]
        if not chunk_token_ids:
            break
        sequence += 1
        chunk_text = enc.decode(chunk_token_ids)
        token_count = len(chunk_token_ids)

        # Attribute to nearest block for provenance metadata
        approx_pos = start / max(len(tokens), 1)
        block_idx = min(int(approx_pos * len(filtered_blocks)), len(filtered_blocks) - 1)
        ref_block = filtered_blocks[block_idx]

        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}_fixed_c{sequence:03d}",
                text=chunk_text,
                document_name=doc.document_name,
                doc_id=doc.doc_id,
                source_url=doc.source_url,
                document_type=doc.document_type.value,
                publication_year=doc.publication_year,
                requires_caution=caution,
                page_number=ref_block.page_number,
                section_title=ref_block.section_title,
                section_number=ref_block.section_number,
                subsection_title=ref_block.subsection_title,
                recommendation_ids=ref_block.recommendation_id or "",
                token_count=token_count,
                is_oversized=token_count > chunk_size,
            )
        )

    return chunks


def chunk_blocks(
    blocks: list[Block],
    doc: SourceDocument,
    settings: Settings | None = None,
    strategy: Literal["section", "fixed"] = "section",
) -> list[Chunk]:
    """Pack blocks into chunks according to chosen strategy."""
    if strategy == "fixed":
        return chunk_blocks_fixed(blocks, doc)
    return chunk_blocks_section(blocks, doc, settings)
