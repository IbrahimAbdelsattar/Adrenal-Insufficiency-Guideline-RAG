"""Unit tests for FallbackEmbedder."""

import pytest

from backend.app.config import Settings
from backend.app.embeddings.fallback import FallbackEmbedder
from backend.app.errors import EmbeddingProviderError


class DummyEmbedder:
    def __init__(self, model_id: str = "dummy", dims: int = 384, fail: bool = False):
        self._model_id = model_id
        self._dims = dims
        self.fail = fail
        self.doc_calls = 0
        self.query_calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.doc_calls += 1
        if self.fail:
            raise EmbeddingProviderError(f"Simulated failure in {self._model_id}")
        return [[0.1 * (i + 1)] * self._dims for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        if self.fail:
            raise EmbeddingProviderError(f"Simulated failure in {self._model_id}")
        return [0.7] * self._dims


class TestFallbackEmbedder:
    """Tests for FallbackEmbedder routing and failure recovery."""

    def test_primary_success_path(self, tmp_path):
        settings = Settings(index_dir=tmp_path, enable_embedding_fallback=True)
        primary = DummyEmbedder("gemini/gemini-embedding-001", dims=3072, fail=False)
        secondary = DummyEmbedder("BAAI/bge-small-en-v1.5", dims=384, fail=False)

        fallback = FallbackEmbedder(primary=primary, secondary=secondary, settings=settings)

        assert fallback.is_fallback_active is False
        assert fallback.model_id == "gemini/gemini-embedding-001"
        assert fallback.dimensions == 3072

        docs = fallback.embed_documents(["chunk 1", "chunk 2"])
        assert len(docs) == 2
        assert len(docs[0]) == 3072
        assert primary.doc_calls == 1
        assert secondary.doc_calls == 0
        assert fallback.is_fallback_active is False

        q = fallback.embed_query("query")
        assert len(q) == 3072
        assert primary.query_calls == 1
        assert secondary.query_calls == 0

    def test_fallback_on_document_embedding_failure(self, tmp_path):
        settings = Settings(index_dir=tmp_path, enable_embedding_fallback=True)
        primary = DummyEmbedder("gemini/gemini-embedding-001", dims=3072, fail=True)
        secondary = DummyEmbedder("BAAI/bge-small-en-v1.5", dims=384, fail=False)

        fallback = FallbackEmbedder(primary=primary, secondary=secondary, settings=settings)

        docs = fallback.embed_documents(["chunk 1", "chunk 2"])
        assert len(docs) == 2
        assert len(docs[0]) == 384
        assert primary.doc_calls == 1
        assert secondary.doc_calls == 1
        assert fallback.is_fallback_active is True
        assert fallback.model_id == "BAAI/bge-small-en-v1.5"
        assert fallback.dimensions == 384

        # Next call goes directly to secondary
        q = fallback.embed_query("subsequent query")
        assert len(q) == 384
        assert primary.query_calls == 0
        assert secondary.query_calls == 1

    def test_fallback_on_query_embedding_failure(self, tmp_path):
        settings = Settings(index_dir=tmp_path, enable_embedding_fallback=True)
        primary = DummyEmbedder("gemini/gemini-embedding-001", dims=3072, fail=True)
        secondary = DummyEmbedder("BAAI/bge-small-en-v1.5", dims=384, fail=False)

        fallback = FallbackEmbedder(primary=primary, secondary=secondary, settings=settings)

        q = fallback.embed_query("clinical query")
        assert len(q) == 384
        assert primary.query_calls == 1
        assert secondary.query_calls == 1
        assert fallback.is_fallback_active is True

    def test_disabled_fallback_propagates_error(self, tmp_path):
        settings = Settings(index_dir=tmp_path, enable_embedding_fallback=False)
        primary = DummyEmbedder("gemini/gemini-embedding-001", dims=3072, fail=True)
        secondary = DummyEmbedder("BAAI/bge-small-en-v1.5", dims=384, fail=False)

        fallback = FallbackEmbedder(
            primary=primary,
            secondary=secondary,
            settings=settings,
            fallback_enabled=False,
        )

        with pytest.raises(EmbeddingProviderError, match="Simulated failure in gemini"):
            fallback.embed_query("query")

        with pytest.raises(EmbeddingProviderError, match="Simulated failure in gemini"):
            fallback.embed_documents(["doc 1"])

        assert fallback.is_fallback_active is False
        assert secondary.query_calls == 0
        assert secondary.doc_calls == 0

    def test_empty_documents_returns_empty(self, tmp_path):
        settings = Settings(index_dir=tmp_path, enable_embedding_fallback=True)
        primary = DummyEmbedder("gemini/gemini-embedding-001", dims=3072, fail=False)
        secondary = DummyEmbedder("BAAI/bge-small-en-v1.5", dims=384, fail=False)

        fallback = FallbackEmbedder(primary=primary, secondary=secondary, settings=settings)
        assert fallback.embed_documents([]) == []
        assert primary.doc_calls == 0
        assert secondary.doc_calls == 0
