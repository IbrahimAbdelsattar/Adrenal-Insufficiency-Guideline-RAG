"""Unit tests for BM25 lexical retriever."""

from backend.app.models import Chunk
from backend.app.retrieval.bm25 import BM25Retriever, tokenize_clinical_text


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


# --- Tokenizer tests ---


class TestTokenizeClinicalText:
    def test_preserves_drug_names(self):
        tokens = tokenize_clinical_text("Hydrocortisone 100mg IV")
        assert "hydrocortisone" in tokens
        assert "100mg" in tokens

    def test_drops_single_char_tokens(self):
        tokens = tokenize_clinical_text("a - b • c")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "c" not in tokens

    def test_lowercases(self):
        tokens = tokenize_clinical_text("Fludrocortisone NICE NG243")
        assert "fludrocortisone" in tokens
        assert "nice" in tokens
        assert "ng243" in tokens

    def test_empty_input(self):
        assert tokenize_clinical_text("") == []


# --- BM25 Retriever tests ---


class TestBM25Retriever:
    def test_finds_exact_keyword(self):
        c1 = _make_chunk(
            "c1", "Hydrocortisone is indicated for primary adrenal insufficiency."
        )
        c2 = _make_chunk(
            "c2", "Prednisolone is an alternative glucocorticoid replacement."
        )

        retriever = BM25Retriever(chunks=[c1, c2])
        results = retriever.search("Hydrocortisone", top_k=2)

        assert len(results) == 2
        assert results[0].chunk.chunk_id == "c1"
        assert results[0].score > results[1].score

    def test_scores_normalised_to_unit_range(self):
        c1 = _make_chunk("c1", "Hydrocortisone dosage for crisis management.")
        retriever = BM25Retriever(chunks=[c1])
        results = retriever.search("Hydrocortisone", top_k=1)

        assert len(results) == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_below_floor_flagging(self):
        c1 = _make_chunk("c1", "Hydrocortisone is the first-line treatment.")
        c2 = _make_chunk(
            "c2",
            "Unrelated content about hospital cafeteria menu options and parking.",
        )

        retriever = BM25Retriever(chunks=[c1, c2])
        results = retriever.search("Hydrocortisone", top_k=2)

        # All results must have the below_floor attribute (Principle VI)
        assert all(hasattr(r, "below_floor") for r in results)
        # The irrelevant chunk should score lower
        assert results[0].score >= results[1].score

    def test_empty_corpus_returns_empty(self):
        retriever = BM25Retriever(chunks=[])
        results = retriever.search("anything", top_k=5)
        assert results == []

    def test_empty_query_returns_empty(self):
        c1 = _make_chunk("c1", "Some content here.")
        retriever = BM25Retriever(chunks=[c1])
        # Single-char query tokens get dropped by tokenizer
        results = retriever.search("a", top_k=5)
        assert results == []

    def test_rank_values_are_one_indexed(self):
        c1 = _make_chunk("c1", "Hydrocortisone treatment for adrenal insufficiency.")
        c2 = _make_chunk("c2", "Fludrocortisone replacement therapy guidelines.")

        retriever = BM25Retriever(chunks=[c1, c2])
        results = retriever.search("Hydrocortisone Fludrocortisone", top_k=2)

        ranks = [r.rank for r in results]
        assert ranks == [1, 2]

    def test_top_k_limits_results(self):
        chunks = [_make_chunk(f"c{i}", f"Content number {i}.") for i in range(10)]
        retriever = BM25Retriever(chunks=chunks)
        results = retriever.search("Content number", top_k=3)
        assert len(results) == 3
