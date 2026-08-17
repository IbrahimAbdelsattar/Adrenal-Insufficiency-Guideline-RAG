"""Unit tests for chunking (T018, FR-011 through FR-014, SC-006).

The critical invariant: a numbered clinical recommendation is atomic. Splitting one
mid-sentence produces a chunk that is both incoherent and dangerously partial.
"""

from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.app.ingestion.chunker import chunk_blocks, count_tokens, is_navigational
from backend.app.ingestion.sectioner import Block
from backend.app.models import DocumentType, SourceDocument

DOC = SourceDocument(
    doc_id="nice_ng243",
    document_name="NICE NG243 — Adrenal insufficiency",
    filename="ng243.pdf",
    publisher="NICE",
    publication_year=2024,
    source_url="https://www.nice.org.uk/guidance/ng243",
    document_type=DocumentType.GUIDELINE,
    credibility_note="Statutory NHS guidance body.",
    license_note="(c) NICE 2024.",
)

SETTINGS = Settings(
    CHUNK_TARGET_TOKENS=600, CHUNK_MIN_TOKENS=400, CHUNK_MAX_TOKENS=800
)


def _block(rec_id: str, words: int, page: int = 9, section: str = "1.2") -> Block:
    return Block(
        text=f"{rec_id} " + " ".join(["hyperpigmentation"] * words),
        page_number=page,
        section_number=section,
        section_title=f"{section} Initial identification and referral",
        subsection_title="When to suspect adrenal insufficiency",
        recommendation_id=rec_id,
    )


class TestAtomicRecommendations:
    def test_no_recommendation_appears_in_two_chunks(self):
        blocks = [_block(f"1.2.{i}", 150) for i in range(1, 12)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)

        seen: list[str] = []
        for chunk in chunks:
            seen.extend(r for r in chunk.recommendation_ids.split(",") if r)
        assert len(seen) == len(set(seen)), "a recommendation was split across chunks"

    def test_every_recommendation_is_present_exactly_once(self):
        blocks = [_block(f"1.2.{i}", 120) for i in range(1, 9)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)
        seen = {
            r
            for chunk in chunks
            for r in chunk.recommendation_ids.split(",")
            if r
        }
        assert seen == {f"1.2.{i}" for i in range(1, 9)}


class TestSizeBand:
    def test_chunks_stay_within_the_band(self):
        blocks = [_block(f"1.2.{i}", 100) for i in range(1, 21)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)
        for chunk in chunks[:-1]:  # the tail may fall under the floor
            if not chunk.is_oversized:
                assert chunk.token_count <= SETTINGS.chunk_max_tokens

    def test_small_siblings_are_packed_together(self):
        blocks = [_block(f"1.2.{i}", 40) for i in range(1, 7)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)
        assert len(chunks) < len(blocks), "small blocks should be packed"


class TestOversized:
    def test_oversized_recommendation_is_flagged_not_truncated(self):
        big = _block("1.3.1", 2000)
        chunks = chunk_blocks([big], DOC, SETTINGS)

        assert len(chunks) == 1
        assert chunks[0].is_oversized
        assert chunks[0].token_count > SETTINGS.chunk_max_tokens
        # Content preserved in full — truncation can invert clinical meaning.
        assert count_tokens(chunks[0].text) == chunks[0].token_count
        assert chunks[0].text.count("hyperpigmentation") == 2000


class TestNavigationalFiltering:
    """Bare cross-references are not standalone evidence (FR-013, SC-005)."""

    @pytest.mark.parametrize(
        "text",
        [
            "Recommendations 1.1.1 to 1.1.9",
            "Recommendations 1.4.10 and 1.4.11",
            "Recommendation 1.7.1",
            "Recommendations 1.2.1, 1.2.2, 1.2.3",
        ],
    )
    def test_cross_reference_stubs_are_navigational(self, text):
        assert is_navigational(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Physiological stress is when a person has a fever or physical trauma.",
            "A set of guidelines for adjusting medication dosages during illness.",
            "Recommendations should be followed when treating adrenal crisis promptly.",
        ],
    )
    def test_real_content_is_not_navigational(self, text):
        assert not is_navigational(text)

    def test_navigational_blocks_are_dropped_from_the_index(self):
        stub = Block(
            text="Recommendations 1.2.1 to 1.2.4",
            page_number=55,
            section_number="1.9",
            section_title="1.9 Managing glucocorticoid withdrawal",
            subsection_title="Initial identification and referral",
            recommendation_id="",
        )
        assert chunk_blocks([stub], DOC, SETTINGS) == []

    def test_a_real_recommendation_is_never_dropped(self):
        """A numbered recommendation survives even if its text looks like a pointer."""
        block = _block("1.2.1", 50)
        assert len(chunk_blocks([block], DOC, SETTINGS)) == 1


class TestSectionBoundaries:
    def test_chunks_do_not_span_sections(self):
        blocks = [_block("1.2.1", 30, section="1.2"), _block("1.3.1", 30, section="1.3")]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)
        assert len(chunks) == 2
        assert {c.section_number for c in chunks} == {"1.2", "1.3"}


class TestMetadata:
    def test_chunk_id_encodes_document_and_page(self):
        chunks = chunk_blocks([_block("1.2.1", 50, page=9)], DOC, SETTINGS)
        assert chunks[0].chunk_id.startswith("nice_ng243_p09_c")

    def test_chunk_ids_are_unique(self):
        blocks = [_block(f"1.2.{i}", 300, page=9) for i in range(1, 10)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS)
        assert len({c.chunk_id for c in chunks}) == len(chunks)

    def test_provenance_is_denormalised_onto_every_chunk(self):
        chunks = chunk_blocks([_block("1.2.1", 50)], DOC, SETTINGS)
        chunk = chunks[0]
        assert chunk.doc_id == "nice_ng243"
        assert chunk.document_name == DOC.document_name
        assert chunk.source_url == DOC.source_url
        assert chunk.publication_year == 2024
        assert chunk.requires_caution is False

    def test_no_metadata_value_is_none(self):
        chunks = chunk_blocks([_block("1.2.1", 50)], DOC, SETTINGS)
        assert all(v is not None for v in chunks[0].to_metadata().values())


class TestFixedSizeChunking:
    def test_fixed_size_chunks_generated(self):
        blocks = [_block(f"1.2.{i}", 100) for i in range(1, 10)]
        chunks = chunk_blocks(blocks, DOC, SETTINGS, strategy="fixed")
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.token_count <= 256
            assert chunk.chunk_id.startswith("nice_ng243_fixed_c")
            assert chunk.doc_id == "nice_ng243"
