"""Regression tests for citation provenance integrity.

Every one of these covers a bug that shipped and produced answers with
missing or wrong document/section/page attribution.
"""

from backend.app.generation.assembler import assemble_evidence, select_sources
from backend.app.generation.citations import (
    extract_citations,
    extract_recommendation_citations,
    resolve_citations,
)
from backend.app.models import Chunk, RetrievalResult

REQUIRED_FIELDS = ("document_name", "page_number")


def _chunk(chunk_id: str, page: int, section: str, rec_ids: str = "") -> Chunk:
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


def _result(chunk: Chunk, rank: int, below_floor: bool = False) -> RetrievalResult:
    return RetrievalResult(chunk=chunk, score=1.0, rank=rank, below_floor=below_floor)


def _assert_complete(citations):
    """Every citation must carry document, section and page."""
    assert citations, "expected at least one citation"
    for c in citations:
        for field in REQUIRED_FIELDS:
            assert c[field], f"citation missing {field}: {c}"
        assert c["section_number"] or c["section_title"], f"citation missing section: {c}"


def test_source_marker_with_trailing_text_is_not_dropped():
    r"""Models write [Source 3, 1.7.1]; the strict `\[Source (\d+)\]` regex lost it."""
    sources = [_result(_chunk("c1", 27, "1.7"), 1)]
    citations = extract_citations("Give hydrocortisone [Source 1, 1.7.1].", sources)
    assert [c["source_id"] for c in citations] == ["1"]
    _assert_complete(citations)


def test_bare_recommendation_marker_resolves_to_page_and_section():
    """Models cite [1.8.6] instead of [Source N]; that must still yield provenance."""
    sources = [
        _result(_chunk("c1", 40, "1.8", rec_ids="1.8.1,1.8.2"), 1),
        _result(_chunk("c2", 44, "1.8", rec_ids="1.8.6,1.8.7"), 2),
    ]
    citations = extract_recommendation_citations("Review adherence [1.8.6].", sources)
    assert len(citations) == 1
    assert citations[0]["page_number"] == 44
    assert citations[0]["resolved_by"] == "recommendation_id"
    _assert_complete(citations)


def test_resolve_citations_returns_empty_when_the_model_cites_nothing():
    """No markers means no provenance -- never fabricate it by attaching every source.

    This used to fall back to attaching every retrieved chunk as a "citation"
    when the model produced no [Source N]/[N.N.N] markers. That proved
    evidence was *retrieved*, not that the answer's claims are *supported* by
    it, and let an ungrounded answer reach the clinician wearing a citation
    list it never earned. Callers must treat an empty result as ungrounded
    (see `validate_grounding` and citations.py's module docstring), not
    silently attribute the answer to everything it was shown.
    """
    sources = [_result(_chunk("c1", 27, "1.7"), 1), _result(_chunk("c2", 28, "1.7"), 2)]
    citations = resolve_citations("Answer with no markers at all.", sources)
    assert citations == []


def test_resolve_citations_prefers_explicit_markers_over_fallback():
    sources = [_result(_chunk("c1", 27, "1.7"), 1), _result(_chunk("c2", 28, "1.7"), 2)]
    citations = resolve_citations("Only this one [Source 2].", sources)
    assert [c["source_id"] for c in citations] == ["2"]
    assert citations[0]["page_number"] == 28
    assert citations[0]["resolved_by"] == "source_marker"


def test_source_numbering_matches_between_prompt_and_citations():
    """[Source N] must index the list the LLM was shown, not the raw results.

    assemble_evidence drops below_floor chunks and renumbers; resolving
    citations against the unfiltered list silently shifts every attribution.
    """
    results = [
        _result(_chunk("weak", 99, "9.9"), 1, below_floor=True),
        _result(_chunk("good", 27, "1.7"), 2),
    ]
    cited = select_sources(results)
    evidence = assemble_evidence(results)

    # The prompt shows exactly one block, and it is the above-floor chunk.
    assert evidence.count("[Source ") == 1
    assert "Page: 27" in evidence
    assert "Page: 99" not in evidence

    citations = resolve_citations("Per the guidance [Source 1].", cited)
    assert citations[0]["page_number"] == 27, "citation must not point at the dropped chunk"
