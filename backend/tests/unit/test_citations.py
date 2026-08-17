"""Unit tests for citation extraction and abstention."""

from backend.app.generation.citations import extract_citations, should_abstain
from backend.app.models import Chunk, RetrievalResult


def _make_chunk(chunk_id: str, text: str) -> Chunk:
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
            "page_number": 1,
            "section_title": "Diagnosis",
            "section_number": "1.2",
            "subsection_title": "",
            "recommendation_ids": "1.2.1",
            "token_count": 10,
            "is_oversized": False,
        },
    )


def test_extract_citations():
    text = "The treatment is hydrocortisone [Source 1]. This is also supported by [Source 2]."
    r1 = RetrievalResult(chunk=_make_chunk("c1", "Hydrocortisone"), score=0.9, rank=1, below_floor=False)
    r2 = RetrievalResult(chunk=_make_chunk("c2", "Supported"), score=0.8, rank=2, below_floor=False)
    
    citations = extract_citations(text, [r1, r2])
    assert len(citations) == 2
    assert citations[0]["source_id"] == "1"
    assert citations[1]["source_id"] == "2"


def test_extract_citations_deduplicates():
    text = "Initial [Source 1] and final [Source 1]."
    r1 = RetrievalResult(chunk=_make_chunk("c1", "Hydrocortisone"), score=0.9, rank=1, below_floor=False)
    
    citations = extract_citations(text, [r1])
    assert len(citations) == 1
    assert citations[0]["source_id"] == "1"


def test_extract_citations_ignores_invalid_indices():
    text = "Valid [Source 1] and invalid [Source 99]."
    r1 = RetrievalResult(chunk=_make_chunk("c1", "Hydrocortisone"), score=0.9, rank=1, below_floor=False)
    
    citations = extract_citations(text, [r1])
    assert len(citations) == 1
    assert citations[0]["source_id"] == "1"


def test_should_abstain_empty():
    assert should_abstain([]) is True


def test_should_abstain_all_below_floor():
    r1 = RetrievalResult(chunk=_make_chunk("c1", "Hydrocortisone"), score=0.1, rank=1, below_floor=True)
    assert should_abstain([r1]) is True


def test_should_not_abstain_mixed():
    r1 = RetrievalResult(chunk=_make_chunk("c1", "Hydrocortisone"), score=0.9, rank=1, below_floor=False)
    r2 = RetrievalResult(chunk=_make_chunk("c2", "Supported"), score=0.1, rank=2, below_floor=True)
    assert should_abstain([r1, r2]) is False
