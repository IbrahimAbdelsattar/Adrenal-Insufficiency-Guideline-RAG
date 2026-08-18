"""End-to-end ingestion over the real corpus with a stubbed embedder (T019).

No API key and no network required — the stub is deterministic, so this runs in CI
and on a laptop with no credit.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app.config import get_settings
from backend.app.ingestion.pipeline import run_ingest
from backend.app.retrieval.store import VectorStore

DIMENSIONS = 32


class StubEmbedder:
    """Deterministic pseudo-embeddings derived from the text hash."""

    model_id = "stub/deterministic-test-embedder"
    dimensions = DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(DIMENSIONS)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """Ingest the real corpus into a throwaway index directory."""
    settings = get_settings().model_copy(update={"index_dir": tmp_path_factory.mktemp("index")})
    store = VectorStore(settings)
    result = run_ingest(settings=settings, embedder=StubEmbedder(), store=store)
    return result, store


class TestIngestProducesAnIndex:
    def test_chunks_were_produced(self, report):
        result, _ = report
        assert result.chunk_count > 0

    def test_index_is_populated(self, report):
        result, store = report
        assert store.count() == result.chunk_count

    def test_manifest_written_with_model(self, report):
        _, store = report
        manifest = store.read_manifest()
        assert manifest is not None
        assert manifest.embedding_model == StubEmbedder.model_id
        assert manifest.chunk_count > 0

    def test_per_document_stats_reported(self, report):
        _, store = report
        manifest = store.read_manifest()
        assert len(manifest.per_document) == 1
        stats = manifest.per_document[0]
        assert stats.doc_id == "nice_ng243"
        assert stats.pages_processed == 63


class TestMetadataCompleteness:
    """SC-002: 100% of chunks carry complete citation metadata."""

    REQUIRED = (
        "document_name",
        "doc_id",
        "source_url",
        "document_type",
        "page_number",
        "section_title",
    )

    def test_no_metadata_field_is_none(self, report):
        _, store = report
        for chunk in store.all_chunks():
            for key, value in chunk.to_metadata().items():
                assert value is not None, f"{chunk.chunk_id}.{key} is None"

    def test_required_fields_are_non_empty(self, report):
        _, store = report
        for chunk in store.all_chunks():
            metadata = chunk.to_metadata()
            for key in self.REQUIRED:
                assert str(metadata[key]).strip(), f"{chunk.chunk_id}.{key} is empty"

    def test_page_numbers_are_within_the_document(self, report):
        _, store = report
        for chunk in store.all_chunks():
            assert 1 <= chunk.page_number <= 63

    def test_chunk_ids_are_unique(self, report):
        _, store = report
        ids = [c.chunk_id for c in store.all_chunks()]
        assert len(ids) == len(set(ids))

    def test_every_chunk_has_text(self, report):
        _, store = report
        assert all(c.text.strip() for c in store.all_chunks())


class TestIdempotence:
    """FR-020: rebuilding is deterministic and produces no duplicates."""

    def test_second_run_yields_the_same_chunk_count(self, report, tmp_path):
        result, _ = report
        settings = get_settings().model_copy(update={"index_dir": tmp_path / "again"})
        second = run_ingest(settings=settings, embedder=StubEmbedder(), store=VectorStore(settings))
        assert second.chunk_count == result.chunk_count

    def test_second_run_yields_the_same_ids(self, report, tmp_path):
        _, store = report
        settings = get_settings().model_copy(update={"index_dir": tmp_path / "ids"})
        second_store = VectorStore(settings)
        run_ingest(settings=settings, embedder=StubEmbedder(), store=second_store)

        first_ids = {c.chunk_id for c in store.all_chunks()}
        second_ids = {c.chunk_id for c in second_store.all_chunks()}
        assert first_ids == second_ids
