"""Ingestion orchestration (FR-015, FR-017, FR-019, FR-020).

registry -> parse -> clean -> section -> chunk -> embed -> index -> manifest

Provenance is denormalised onto every chunk during chunking, so retrieval never needs
a second lookup and metadata cannot drift from its vector (Constitution Principle II).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.ingestion import cleaner, parser, registry
from backend.app.ingestion.chunker import chunk_blocks
from backend.app.ingestion.sectioner import detect_blocks
from backend.app.models import Chunk, IndexManifest, PerDocumentStats, SourceDocument
from backend.app.retrieval.store import VectorStore

Reporter = Callable[[str], None]


def _silent(_: str) -> None:
    pass


@dataclass
class DocumentReport:
    doc_id: str
    pages_processed: int
    pages_empty: int
    boilerplate_patterns: int
    block_count: int
    recommendation_count: int
    chunk_count: int


@dataclass
class IngestReport:
    documents: list[DocumentReport] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    manifest: IndexManifest | None = None
    dry_run: bool = False
    elapsed_seconds: float = 0.0

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def oversized_count(self) -> int:
        return sum(1 for c in self.chunks if c.is_oversized)


def _process_document(
    doc: SourceDocument, settings: Settings, report: Reporter
) -> tuple[list[Chunk], DocumentReport]:
    path = settings.corpus_path / doc.filename

    pages = parser.parse_pdf(path)
    report(f"Parsing    {doc.doc_id} ... {len(pages)} pages")

    cleaned = cleaner.clean(pages, settings.boilerplate_page_ratio)
    report(
        f"Cleaning   removed {len(cleaned.boilerplate)} boilerplate pattern(s); "
        f"{cleaned.pages_empty} page(s) empty after cleaning"
    )

    blocks = detect_blocks(cleaned.pages)
    recommendations = sum(1 for b in blocks if b.recommendation_id)
    sections = len({b.section_number for b in blocks if b.section_number})
    report(
        f"Sections   detected {sections} section(s), "
        f"{recommendations} numbered recommendation(s)"
    )

    chunks = chunk_blocks(blocks, doc, settings)
    if chunks:
        sizes = [c.token_count for c in chunks]
        report(
            f"Chunking   {len(chunks)} chunks | mean {sum(sizes) // len(sizes)} tok | "
            f"min {min(sizes)} | max {max(sizes)} | "
            f"oversized {sum(1 for c in chunks if c.is_oversized)}"
        )

    return chunks, DocumentReport(
        doc_id=doc.doc_id,
        pages_processed=cleaned.pages_processed,
        pages_empty=cleaned.pages_empty,
        boilerplate_patterns=len(cleaned.boilerplate),
        block_count=len(blocks),
        recommendation_count=recommendations,
        chunk_count=len(chunks),
    )


def run_ingest(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
    doc_id: str | None = None,
    dry_run: bool = False,
    report: Reporter | None = None,
) -> IngestReport:
    """Rebuild the index from the registered corpus.

    Idempotent: the collection is rebuilt from scratch each run, and the swap only
    happens on success, so a failure leaves the previous index queryable (FR-020).
    """
    settings = settings or get_settings()
    report = report or _silent
    started = time.perf_counter()

    # Fail closed before any parsing work (FR-002).
    documents = registry.validate_corpus(settings)
    if doc_id:
        documents = [d for d in documents if d.doc_id == doc_id]
        if not documents:
            raise registry.ConfigurationError(f"No registered document '{doc_id}'.")

    report(
        f"Registry:  {len(documents)} document(s) registered, "
        f"{len(registry.list_corpus_pdfs(settings))} PDF(s) found, 0 unregistered"
    )

    all_chunks: list[Chunk] = []
    per_document: list[DocumentReport] = []
    for doc in documents:
        chunks, doc_report = _process_document(doc, settings, report)
        all_chunks.extend(chunks)
        per_document.append(doc_report)

    result = IngestReport(
        documents=per_document, chunks=all_chunks, dry_run=dry_run
    )

    if dry_run:
        report("Dry run    no embeddings requested, index untouched")
        result.elapsed_seconds = time.perf_counter() - started
        return result

    if embedder is None:
        # Imported here so --dry-run works without an API key configured.
        from backend.app.embeddings.openrouter import OpenRouterEmbedder

        embedder = OpenRouterEmbedder(settings)

    report(f"Embedding  {len(all_chunks)} chunks via {embedder.model_id} ...")
    vectors = embedder.embed_documents([c.text for c in all_chunks])

    store = store or VectorStore(settings)
    store.build(all_chunks, vectors)
    report(
        f"Indexing   wrote {len(all_chunks)} entries to {settings.index_path} "
        f"(collection: {store.collection_name})"
    )

    manifest = IndexManifest(
        built_at=datetime.now(timezone.utc),
        embedding_model=embedder.model_id,
        embedding_dimensions=embedder.dimensions or (len(vectors[0]) if vectors else 0),
        chunk_target_tokens=settings.chunk_target_tokens,
        chunk_min_tokens=settings.chunk_min_tokens,
        chunk_max_tokens=settings.chunk_max_tokens,
        document_count=len(documents),
        chunk_count=len(all_chunks),
        oversized_chunk_count=result.oversized_count,
        per_document=[
            PerDocumentStats(
                doc_id=d.doc_id,
                pages_processed=d.pages_processed,
                pages_empty=d.pages_empty,
                chunk_count=d.chunk_count,
            )
            for d in per_document
        ],
    )
    store.write_manifest(manifest)
    report(f"Manifest   {settings.manifest_path}")

    result.manifest = manifest
    result.elapsed_seconds = time.perf_counter() - started
    return result
