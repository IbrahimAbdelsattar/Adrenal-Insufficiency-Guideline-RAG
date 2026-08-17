"""Unit tests for BM25 lexical retriever (Day 2 hybrid search)."""

from __future__ import annotations

import pytest

from backend.app.models import Chunk
from backend.app.retrieval.bm25 import BM25Retriever, tokenize_clinical_text


class MockStore:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks

    def all_chunks(self) -> list[Chunk]:
        return self._chunks


@pytest.fixture
def mock_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="chunk_01",
            text="Immediate management of acute adrenal crisis requires 100mg IV hydrocortisone.",
            document_name="NICE NG243",
            doc_id="nice_ng243",
            source_url="https://nice.org.uk/ng243",
            document_type="guideline",
            publication_year=2024,
            requires_caution=False,
            page_number=14,
            section_number="1.7",
            section_title="1.7 Emergency management of adrenal crisis",
            recommendation_ids="1.7.1",
            token_count=50,
        ),
        Chunk(
            chunk_id="chunk_02",
            text="Routine replacement in adults consists of oral hydrocortisone 15-25mg daily.",
            document_name="NICE NG243",
            doc_id="nice_ng243",
            source_url="https://nice.org.uk/ng243",
            document_type="guideline",
            publication_year=2024,
            requires_caution=False,
            page_number=10,
            section_number="1.3",
            section_title="1.3 Pharmacological management",
            recommendation_ids="1.3.1",
            token_count=45,
        ),
        Chunk(
            chunk_id="chunk_03",
            text="For sick day rules during fever over 38C, double the normal daily oral dose.",
            document_name="NICE NG243",
            doc_id="nice_ng243",
            source_url="https://nice.org.uk/ng243",
            document_type="guideline",
            publication_year=2024,
            requires_caution=False,
            page_number=12,
            section_number="1.4",
            section_title="1.4 Managing during physiological stress",
            recommendation_ids="1.4.1",
            token_count=48,
        ),
    ]


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
        tokens = tokenize_clinical_text("Hydrocortisone 100mg IV for recommendation 1.7.1")
        assert "hydrocortisone" in tokens
        assert "100mg" in tokens
        assert "1.7.1" in tokens
        assert "for" not in tokens  # stopword removed

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
    def test_finds_exact_keyword(self, mock_chunks):
        store = MockStore(mock_chunks)
        retriever = BM25Retriever(store=store)
        results = retriever.search("100mg hydrocortisone emergency crisis", top_k=2)
        assert len(results) == 2
        assert results[0].chunk.chunk_id == "chunk_01"
        assert results[0].rank == 1
        assert results[0].score > results[1].score

    def test_scores_normalised_to_unit_range(self):
        c1 = _make_chunk("c1", "Hydrocortisone dosage for crisis management.")
        retriever = BM25Retriever(chunks=[c1])
        results = retriever.search("Hydrocortisone", top_k=1)
        assert len(results) == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_below_floor_flagging(self):
        c1 = _make_chunk("c1", "Hydrocortisone is the first-line treatment.")
        c2 = _make_chunk("c2", "Unrelated content about hospital cafeteria menu.")
        retriever = BM25Retriever(chunks=[c1, c2])
        results = retriever.search("Hydrocortisone", top_k=2)
        assert all(hasattr(r, "below_floor") for r in results)
        assert results[0].score >= results[1].score

    def test_empty_corpus_returns_empty(self):
        retriever = BM25Retriever(chunks=[])
        results = retriever.search("anything", top_k=5)
        assert results == []

    def test_empty_query_returns_empty(self):
        c1 = _make_chunk("c1", "Some content here.")
        retriever = BM25Retriever(chunks=[c1])
        results = retriever.search("", top_k=5)
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
