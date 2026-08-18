"""Ingestion orchestration (FR-015, FR-017, FR-019, FR-020).

registry -> parse -> clean -> section -> chunk -> embed -> index -> manifest

Provenance is denormalised onto every chunk during chunking, so retrieval never needs
a second lookup and metadata cannot drift from its vector (Constitution Principle II).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.app import graph
from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.ingestion import cleaner, parser, registry
from backend.app.ingestion.chunker import chunk_blocks
from backend.app.ingestion.sectioner import detect_blocks
from backend.app.models import Chunk, IndexManifest, PerDocumentStats, SourceDocument
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)

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
    stage_start = time.perf_counter()

    pages = parser.parse_pdf(path)
    report(f"Parsing    {doc.doc_id} ... {len(pages)} pages")
    logger.info(
        "parsed doc_id=%s pages=%d elapsed=%.2fs",
        doc.doc_id,
        len(pages),
        time.perf_counter() - stage_start,
    )

    cleaned = cleaner.clean(pages, settings.boilerplate_page_ratio)
    report(
        f"Cleaning   removed {len(cleaned.boilerplate)} boilerplate pattern(s); "
        f"{cleaned.pages_empty} page(s) empty after cleaning"
    )

    blocks = detect_blocks(cleaned.pages)
    recommendations = sum(1 for b in blocks if b.recommendation_id)
    sections = len({b.section_number for b in blocks if b.section_number})
    report(
        f"Sections   detected {sections} section(s), {recommendations} numbered recommendation(s)"
    )

    chunks = chunk_blocks(blocks, doc, settings)
    if chunks:
        sizes = [c.token_count for c in chunks]
        report(
            f"Chunking   {len(chunks)} chunks | mean {sum(sizes) // len(sizes)} tok | "
            f"min {min(sizes)} | max {max(sizes)} | "
            f"oversized {sum(1 for c in chunks if c.is_oversized)}"
        )
        logger.info(
            "chunked doc_id=%s chunks=%d mean_tokens=%d oversized=%d "
            "sections=%d recommendations=%d total_elapsed=%.2fs",
            doc.doc_id,
            len(chunks),
            sum(sizes) // len(sizes),
            sum(1 for c in chunks if c.is_oversized),
            sections,
            recommendations,
            time.perf_counter() - stage_start,
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


def _embed_in_batches(
    embedder: Embedder,
    chunks: list[Chunk],
    batch_size: int,
    report: Reporter,
) -> list[list[float]]:
    """Embed chunks in fixed-size batches instead of one giant request.

    Guards the pipeline (not just a specific embedder implementation) against
    memory blowups / provider timeouts once the corpus grows into the
    thousands of chunks (see EMBEDDING_BATCH_SIZE, default 32). Any Embedder
    passed in — OpenRouterEmbedder, a test double, a future provider — gets
    this protection regardless of whether it batches internally.
    """
    batch_size = max(1, batch_size)
    texts = [c.text for c in chunks]
    total = len(texts)
    total_batches = (total + batch_size - 1) // batch_size if total else 0

    vectors: list[list[float]] = []
    for batch_num, start in enumerate(range(0, total, batch_size), start=1):
        batch = texts[start : start + batch_size]
        report(
            f"Embedding  batch {batch_num}/{total_batches} "
            f"({len(batch)} chunks, {start + len(batch)}/{total} total)"
        )
        vectors.extend(embedder.embed_documents(batch))

    return vectors


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

    result = IngestReport(documents=per_document, chunks=all_chunks, dry_run=dry_run)

    if dry_run:
        report("Dry run    no embeddings requested, index untouched")
        result.elapsed_seconds = time.perf_counter() - started
        return result

    if embedder is None:
        # Imported here so --dry-run works without an API key configured.
        from backend.app.embeddings.openrouter import OpenRouterEmbedder

        embedder = OpenRouterEmbedder(settings)

    report(f"Embedding  {len(all_chunks)} chunks via {embedder.model_id} ...")
    embed_start = time.perf_counter()
    vectors = _embed_in_batches(embedder, all_chunks, settings.embedding_batch_size, report)
    logger.info(
        "embedded chunks=%d model=%s elapsed=%.2fs",
        len(all_chunks),
        embedder.model_id,
        time.perf_counter() - embed_start,
    )

    store = store or VectorStore(settings)
    store.build(all_chunks, vectors)
    report(
        f"Indexing   wrote {len(all_chunks)} entries to {settings.index_path} "
        f"(collection: {store.collection_name})"
    )

    manifest = IndexManifest(
        built_at=datetime.now(UTC),
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

    adjacency = graph.build_graph(all_chunks)
    graph_path = graph.save_graph(adjacency, settings.index_path)
    report(
        f"Graph      {graph.edge_count(adjacency)} edge(s) across "
        f"{len(adjacency)} node(s) -> {graph_path}"
    )

    result.manifest = manifest
    result.elapsed_seconds = time.perf_counter() - started
    return result
