"""Unit tests for BM25 Lexical Retriever (Day 2 Lab)."""

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


def test_tokenize_clinical_text():
    tokens = tokenize_clinical_text("Hydrocortisone 100mg IV for recommendation 1.7.1")
    assert "hydrocortisone" in tokens
    assert "100mg" in tokens
    assert "1.7.1" in tokens
    assert "for" not in tokens  # stopword removed


def test_bm25_search_ranking(mock_chunks):
    store = MockStore(mock_chunks)
    retriever = BM25Retriever(store=store)

    results = retriever.search("100mg hydrocortisone emergency crisis", top_k=2)
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "chunk_01"
    assert results[0].rank == 1
    assert results[0].score > results[1].score


def test_bm25_empty_query(mock_chunks):
    store = MockStore(mock_chunks)
    retriever = BM25Retriever(store=store)
    assert retriever.search("", top_k=5) == []
