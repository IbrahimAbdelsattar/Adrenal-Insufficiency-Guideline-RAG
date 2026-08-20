"""Integration tests for Dense and Hybrid retrieval with embedding fallback."""



from backend.app.config import Settings
from backend.app.embeddings.fallback import FallbackEmbedder
from backend.app.errors import EmbeddingProviderError
from backend.app.models import Chunk
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.store import VectorStore


def _make_chunk(chunk_id: str, text: str, page: int = 1) -> Chunk:
    return Chunk.from_stored(
        chunk_id,
        text,
        {
            "doc_id": "test_doc",
            "document_name": "Test Guideline",
            "source_url": "https://example.com/test",
            "document_type": "guideline",
            "publication_year": 2024,
            "requires_caution": False,
            "page_number": page,
            "section_title": "Emergency Treatment",
            "section_number": "1.1",
            "subsection_title": "Adrenal Crisis",
            "recommendation_ids": "REC-01",
            "token_count": 15,
            "is_oversized": False,
        },
    )


class MockFailingPrimaryEmbedder:
    @property
    def model_id(self) -> str:
        return "gemini/gemini-embedding-001"

    @property
    def dimensions(self) -> int:
        return 3072

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderError("Gemini API quota exhausted (HTTP 429)")

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingProviderError("Gemini API quota exhausted (HTTP 429)")


class MockLocalSecondaryEmbedder:
    @property
    def model_id(self) -> str:
        return "BAAI/bge-small-en-v1.5"

    @property
    def dimensions(self) -> int:
        return 4

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


class TestEmbeddingFallbackRetrieval:
    """End-to-end integration tests for retrieval when primary embedding fails."""

    def test_dense_retriever_fallback_to_local_collection(self, tmp_path):
        settings = Settings(
            index_dir=tmp_path,
            enable_embedding_fallback=True,
            chroma_collection="test_primary",
            fallback_chroma_collection="test_local",
            top_k=2,
            relevance_floor=0.1,
        )
        store = VectorStore(settings)

        c1 = _make_chunk("c1", "Hydrocortisone 100mg IV immediately for adrenal crisis.")
        c2 = _make_chunk("c2", "General supportive care and hydration.")

        # Build fallback collection with 4-dim vectors
        local_vectors = [[1.0, 0.0, 0.0, 0.0], [0.1, 0.9, 0.0, 0.0]]
        store.build([c1, c2], local_vectors, collection_name=settings.fallback_chroma_collection)

        fallback_embedder = FallbackEmbedder(
            primary=MockFailingPrimaryEmbedder(),
            secondary=MockLocalSecondaryEmbedder(),
            settings=settings,
        )

        dense = DenseRetriever(embedder=fallback_embedder, store=store, settings=settings)
        results = dense.search("hydrocortisone emergency dose")

        assert len(results) >= 1
        assert results[0].chunk.chunk_id == "c1"
        assert fallback_embedder.is_fallback_active is True
        assert results[0].score > 0.5

    def test_hybrid_retriever_resilience_on_failing_gemini(self, tmp_path):
        settings = Settings(
            index_dir=tmp_path,
            enable_embedding_fallback=True,
            chroma_collection="test_primary",
            fallback_chroma_collection="test_local",
            top_k=2,
            relevance_floor=0.1,
        )
        store = VectorStore(settings)

        c1 = _make_chunk("c1", "Hydrocortisone 100mg IV immediately for adrenal crisis.")
        c2 = _make_chunk("c2", "General supportive care and hydration.")

        # Build fallback collection
        local_vectors = [[1.0, 0.0, 0.0, 0.0], [0.1, 0.9, 0.0, 0.0]]
        store.build([c1, c2], local_vectors, collection_name=settings.fallback_chroma_collection)

        fallback_embedder = FallbackEmbedder(
            primary=MockFailingPrimaryEmbedder(),
            secondary=MockLocalSecondaryEmbedder(),
            settings=settings,
        )

        dense = DenseRetriever(embedder=fallback_embedder, store=store, settings=settings)
        bm25 = BM25Retriever(store=store, settings=settings)
        hybrid = HybridRetriever(
            dense_retriever=dense,
            bm25_retriever=bm25,
            store=store,
            settings=settings,
        )

        results = hybrid.search("hydrocortisone adrenal crisis")
        assert len(results) > 0
        assert results[0].chunk.chunk_id == "c1"
