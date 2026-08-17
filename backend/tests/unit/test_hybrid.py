"""Unit tests for the Hybrid Retriever with RRF fusion."""

from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker


def _make_chunk(chunk_id: str, text: str, page: int = 1) -> Chunk:
    """Create a minimal Chunk for testing."""
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
            "section_title": "",
            "section_number": "1.1",
            "subsection_title": "",
            "recommendation_ids": "",
            "token_count": 10,
            "is_oversized": False,
        },
    )


class StubDenseRetriever:
    """Minimal dense retriever stub for unit tests.

    Avoids needing ChromaDB or an embedding API key.
    """

    def __init__(self, results: list[RetrievalResult] | None = None):
        self._results = results or []

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        return self._results[:top_k]


def _make_dense_results(chunks: list[Chunk]) -> list[RetrievalResult]:
    """Build synthetic dense results with descending scores."""
    return [
        RetrievalResult(
            chunk=c, score=1.0 - i * 0.1, rank=i + 1, below_floor=False
        )
        for i, c in enumerate(chunks)
    ]


class TestHybridRetriever:
    def test_combines_bm25_and_dense(self):
        c1 = _make_chunk(
            "c1", "Hydrocortisone is used for adrenal crisis management."
        )
        c2 = _make_chunk(
            "c2", "NICE Guideline NG243 scope and recommendation overview."
        )

        dense_stub = StubDenseRetriever(_make_dense_results([c1, c2]))
        bm25 = BM25Retriever(chunks=[c1, c2])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("Hydrocortisone crisis", top_k=2)

        assert len(results) > 0
        assert results[0].chunk.chunk_id == "c1"

    def test_below_floor_flag_present(self):
        c1 = _make_chunk("c1", "Clinical content about adrenal insufficiency.")

        dense_stub = StubDenseRetriever(_make_dense_results([c1]))
        bm25 = BM25Retriever(chunks=[c1])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("adrenal insufficiency", top_k=1)

        assert len(results) == 1
        assert hasattr(results[0], "below_floor")

    def test_rrf_boosts_chunks_in_both_retrievers(self):
        """A chunk ranked well in both retrievers should be boosted by RRF."""
        c1 = _make_chunk(
            "c1", "Hydrocortisone dosage for emergency adrenal crisis."
        )
        c2 = _make_chunk(
            "c2", "General overview of hospital administration processes."
        )
        c3 = _make_chunk(
            "c3", "Fludrocortisone for mineralocorticoid replacement therapy."
        )

        # Dense: c1 > c3 > c2
        dense_results = [
            RetrievalResult(chunk=c1, score=0.9, rank=1, below_floor=False),
            RetrievalResult(chunk=c3, score=0.7, rank=2, below_floor=False),
            RetrievalResult(chunk=c2, score=0.3, rank=3, below_floor=True),
        ]
        dense_stub = StubDenseRetriever(dense_results)
        # BM25 should also rank c1 first for "Hydrocortisone crisis"
        bm25 = BM25Retriever(chunks=[c1, c2, c3])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("Hydrocortisone crisis", top_k=3)

        assert len(results) == 3
        # c1 should be top since it appears in both retrievers
        assert results[0].chunk.chunk_id == "c1"

    def test_without_reranker(self):
        c1 = _make_chunk("c1", "Hydrocortisone management content.")

        dense_stub = StubDenseRetriever(_make_dense_results([c1]))
        bm25 = BM25Retriever(chunks=[c1])

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            use_reranker=False,
        )
        results = hybrid.search("Hydrocortisone", top_k=1)

        assert len(results) == 1

    def test_empty_results_from_both(self):
        dense_stub = StubDenseRetriever([])
        bm25 = BM25Retriever(chunks=[])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("anything", top_k=5)

        assert results == []

    def test_ranks_are_one_indexed(self):
        c1 = _make_chunk("c1", "Hydrocortisone for adrenal crisis.")
        c2 = _make_chunk("c2", "Prednisolone alternative treatment.")

        dense_stub = StubDenseRetriever(_make_dense_results([c1, c2]))
        bm25 = BM25Retriever(chunks=[c1, c2])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("Hydrocortisone Prednisolone", top_k=2)

        ranks = [r.rank for r in results]
        assert ranks == [1, 2]

    def test_scores_in_valid_range(self):
        c1 = _make_chunk("c1", "Hydrocortisone treatment guidelines.")
        c2 = _make_chunk("c2", "Fludrocortisone dosage information.")

        dense_stub = StubDenseRetriever(_make_dense_results([c1, c2]))
        bm25 = BM25Retriever(chunks=[c1, c2])
        reranker = CrossEncoderReranker(disabled=True)

        hybrid = HybridRetriever(
            dense_retriever=dense_stub,
            bm25_retriever=bm25,
            reranker=reranker,
        )
        results = hybrid.search("treatment", top_k=2)

        for r in results:
            assert 0.0 <= r.score <= 1.0
