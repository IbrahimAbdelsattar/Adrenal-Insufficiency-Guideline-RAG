"""Unit tests for citation-grounding enforcement (validate_grounding).

Covers the exact failure this replaces: an answer reaching a clinician with
a "citation" list that proves evidence was retrieved but not that any
specific claim -- especially a dose, route, timing, threshold, or emergency
instruction -- is actually supported by it.
"""

from backend.app.generation.citations import validate_grounding
from backend.app.models import Chunk, RetrievalResult


def _chunk(chunk_id: str, page: int, section: str = "1.7", rec_ids: str = "") -> Chunk:
    return Chunk.from_stored(
        chunk_id,
        f"Guidance text for {section}",
        {
            "doc_id": "nice_ng243",
            "document_name": "NICE NG243",
            "source_url": "https://www.nice.org.uk/guidance/ng243",
            "document_type": "guideline",
            "publication_year": 2024,
            "requires_caution": False,
            "page_number": page,
            "section_title": f"Section {section}",
            "section_number": section,
            "subsection_title": "",
            "recommendation_ids": rec_ids,
            "token_count": 10,
            "is_oversized": False,
        },
    )


def _result(chunk: Chunk, rank: int = 1) -> RetrievalResult:
    return RetrievalResult(chunk=chunk, score=1.0, rank=rank, below_floor=False)


def test_fully_cited_clinical_answer_is_verified():
    sources = [_result(_chunk("c1", 27))]
    text = "Give 100mg hydrocortisone IV immediately [Source 1]."
    result = validate_grounding(text, sources)
    assert result.status == "verified"
    assert len(result.citations) == 1


def test_uncited_dose_claim_fails_even_when_other_text_is_cited():
    """The bug: a citation elsewhere in the answer must not cover an uncited claim."""
    sources = [_result(_chunk("c1", 27))]
    text = (
        "Adrenal insufficiency is managed with glucocorticoid replacement [Source 1].\n"
        "Give 100mg hydrocortisone IV immediately."
    )
    result = validate_grounding(text, sources)
    assert result.status == "failed"
    assert result.reason == "unsupported_clinical_claim"
    assert result.citations == []
    assert any("100mg" in c or "hydrocortisone" in c for c in result.unsupported_claims)


def test_out_of_range_source_marker_is_rejected():
    sources = [_result(_chunk("c1", 27))]
    text = "Give 100mg hydrocortisone IV [Source 5]."
    result = validate_grounding(text, sources)
    assert result.status == "failed"
    assert result.reason == "invalid_citation_marker"
    assert result.invalid_markers == ["5"]
    assert result.citations == []


def test_zero_index_source_marker_is_rejected():
    sources = [_result(_chunk("c1", 27))]
    result = validate_grounding("Per [Source 0].", sources)
    assert result.status == "failed"
    assert result.reason == "invalid_citation_marker"


def test_no_evidence_at_all_fails_closed():
    result = validate_grounding("Take 100mg hydrocortisone [Source 1].", [])
    assert result.status == "failed"
    assert result.reason == "no_sources"


def test_bare_recommendation_marker_counts_as_a_citation():
    """Models sometimes cite the guideline's own numbering; that still resolves exactly."""
    sources = [_result(_chunk("c1", 40, rec_ids="1.7.1"))]
    text = "Give 100mg hydrocortisone IV immediately [1.7.1]."
    result = validate_grounding(text, sources)
    assert result.status == "verified"


def test_non_clinical_prose_needs_no_citation():
    sources = [_result(_chunk("c1", 27))]
    text = "The evidence does not address paediatric dosing for this scenario."
    result = validate_grounding(text, sources)
    assert result.status == "verified"
    assert result.citations == []


def test_threshold_claim_without_citation_fails():
    sources = [_result(_chunk("c1", 27))]
    text = "Diagnosis is confirmed when morning cortisol is <100 nmol/L."
    result = validate_grounding(text, sources)
    assert result.status == "failed"
    assert result.reason == "unsupported_clinical_claim"


def test_emergency_instruction_without_citation_fails():
    sources = [_result(_chunk("c1", 27))]
    text = "In a suspected adrenal crisis, call 999 immediately."
    result = validate_grounding(text, sources)
    assert result.status == "failed"
    assert result.reason == "unsupported_clinical_claim"


def test_multiple_cited_clinical_claims_all_verify():
    sources = [_result(_chunk("c1", 27)), _result(_chunk("c2", 28))]
    text = (
        "Give 100mg hydrocortisone IV immediately [Source 1].\n"
        "Monitor cortisol every 6 hours during the acute phase [Source 2]."
    )
    result = validate_grounding(text, sources)
    assert result.status == "verified"
    assert {c["source_id"] for c in result.citations} == {"1", "2"}
