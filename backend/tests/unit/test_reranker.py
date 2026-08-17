"""Unit tests for Cross-Encoder reranker with fallback logic."""

from backend.app.models import Chunk
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


class TestCrossEncoderRerankerFallback:
    """Test fallback behaviour when the model is disabled or unavailable."""

    def test_disabled_reranker_returns_all_chunks(self):
        c1 = _make_chunk("c1", "Hydrocortisone dosage for adrenal crisis.")
        c2 = _make_chunk("c2", "General guidelines for clinical documentation.")

        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("Hydrocortisone dosage", [c1, c2])

        assert len(scored) == 2

    def test_disabled_reranker_preserves_input_order(self):
        c1 = _make_chunk("c1", "First chunk about adrenal crisis.")
        c2 = _make_chunk("c2", "Second chunk about steroid replacement.")
        c3 = _make_chunk("c3", "Third chunk about sick-day rules.")

        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("adrenal crisis", [c1, c2, c3])

        # Fallback preserves input order
        assert scored[0][0].chunk_id == "c1"
        assert scored[1][0].chunk_id == "c2"
        assert scored[2][0].chunk_id == "c3"

    def test_disabled_reranker_scores_in_unit_range(self):
        c1 = _make_chunk("c1", "Some clinical content.")
        c2 = _make_chunk("c2", "Other clinical content.")

        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("clinical question", [c1, c2])

        for _, score in scored:
            assert 0.0 <= score <= 1.0

    def test_disabled_reranker_first_score_higher_than_last(self):
        chunks = [_make_chunk(f"c{i}", f"Chunk number {i} content.") for i in range(5)]

        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("query", chunks)

        assert scored[0][1] >= scored[-1][1]

    def test_empty_chunks_returns_empty(self):
        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("any query", [])
        assert scored == []

    def test_is_available_false_when_disabled(self):
        reranker = CrossEncoderReranker(disabled=True)
        assert reranker.is_available is False

    def test_single_chunk(self):
        c1 = _make_chunk("c1", "Only one chunk.")
        reranker = CrossEncoderReranker(disabled=True)
        scored = reranker.rerank("query", [c1])

        assert len(scored) == 1
        assert scored[0][0].chunk_id == "c1"
        assert scored[0][1] > 0.0
