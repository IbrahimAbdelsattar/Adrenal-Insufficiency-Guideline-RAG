"""Unit tests for evidence assembly logic."""

from backend.app.generation.assembler import assemble_evidence
from backend.app.models import Chunk, RetrievalResult


def _make_chunk(chunk_id: str, text: str, page: int = 1, requires_caution: bool = False) -> Chunk:
    return Chunk.from_stored(
        chunk_id,
        text,
        {
            "doc_id": "test_doc",
            "document_name": "Test Guideline",
            "source_url": "https://example.com/test",
            "document_type": "guideline",
            "publication_year": 2024,
            "requires_caution": requires_caution,
            "page_number": page,
            "section_title": "Diagnosis",
            "section_number": "1.2",
            "subsection_title": "",
            "recommendation_ids": "1.2.1",
            "token_count": 10,
            "is_oversized": False,
        },
    )


def test_assemble_evidence_empty():
    text = assemble_evidence([])
    assert "No relevant evidence found." in text


def test_assemble_evidence_formats_correctly():
    c1 = _make_chunk("c1", "Hydrocortisone is recommended.")
    r1 = RetrievalResult(chunk=c1, score=0.9, rank=1, below_floor=False)

    text = assemble_evidence([r1])
    assert "[Source 1]" in text
    assert "Document: Test Guideline" in text
    assert "Section: 1.2 Diagnosis" in text
    assert "Recommendations: 1.2.1" in text
    assert "Page: 1" in text
    assert "Hydrocortisone is recommended." in text


def test_assemble_evidence_filters_below_floor_if_mixed():
    c1 = _make_chunk("c1", "Good chunk")
    r1 = RetrievalResult(chunk=c1, score=0.9, rank=1, below_floor=False)

    c2 = _make_chunk("c2", "Bad chunk")
    r2 = RetrievalResult(chunk=c2, score=0.1, rank=2, below_floor=True)

    text = assemble_evidence([r1, r2])
    assert "[Source 1]" in text
    assert "Good chunk" in text
    assert "Bad chunk" not in text
    assert "[Source 2]" not in text


def test_assemble_evidence_keeps_below_floor_if_all_below():
    c1 = _make_chunk("c1", "Bad chunk 1")
    r1 = RetrievalResult(chunk=c1, score=0.1, rank=1, below_floor=True)

    c2 = _make_chunk("c2", "Bad chunk 2")
    r2 = RetrievalResult(chunk=c2, score=0.05, rank=2, below_floor=True)

    text = assemble_evidence([r1, r2])
    assert "[Source 1]" in text
    assert "Bad chunk 1" in text
    assert "[Source 2]" in text
    assert "Bad chunk 2" in text


def test_assemble_evidence_caution_flag():
    c1 = _make_chunk("c1", "Old chunk", requires_caution=True)
    r1 = RetrievalResult(chunk=c1, score=0.9, rank=1, below_floor=False)

    text = assemble_evidence([r1])
    assert "CAUTION: This document requires caution" in text
