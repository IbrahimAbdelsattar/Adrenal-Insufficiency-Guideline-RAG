"""Regression tests for the out-of-scope guardrail.

The hybrid retriever normalises RRF scores by the top hit, so `score` is 1.0
for every query -- including "how do I bake sourdough bread". Comparing that
against a threshold classified unrelated questions as in_scope and answered
them from the clinical corpus.
"""

from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.scope import classify_scope

SCOPE_THRESHOLD = 0.58


def _chunk(chunk_id: str) -> Chunk:
    return Chunk.from_stored(
        chunk_id,
        "text",
        {
            "doc_id": "nice_ng243",
            "document_name": "NICE NG243",
            "source_url": "",
            "document_type": "guideline",
            "publication_year": 2024,
            "requires_caution": False,
            "page_number": 1,
            "section_title": "S",
            "section_number": "1.1",
            "subsection_title": "",
            "recommendation_ids": "",
            "token_count": 10,
            "is_oversized": False,
        },
    )


def _result(dense: float, below_floor: bool) -> RetrievalResult:
    # score=1.0 mirrors the retriever: RRF normalised against the top hit.
    return RetrievalResult(
        chunk=_chunk("c1"),
        score=1.0,
        rank=1,
        below_floor=below_floor,
        dense_score=dense,
        retriever_mode="hybrid",
    )


def test_absolute_relevance_prefers_dense_over_normalised_score():
    assert _result(0.44, True).absolute_relevance == 0.44


def test_absolute_relevance_prefers_reranker_when_present():
    r = RetrievalResult(
        chunk=_chunk("c1"),
        score=1.0,
        rank=1,
        below_floor=False,
        dense_score=0.44,
        rerank_score=0.91,
        retriever_mode="hybrid_rerank",
    )
    assert r.absolute_relevance == 0.91


def test_unrelated_query_is_out_of_scope_despite_score_of_one():
    """Measured: unrelated queries top out at ~0.526 dense cosine."""
    status, _, shown = classify_scope([_result(0.44, True)], SCOPE_THRESHOLD)
    assert status == "out_of_scope"
    assert shown == []


def test_clinical_query_stays_in_scope():
    """Measured: in-scope queries start at ~0.700 dense cosine."""
    status, _, shown = classify_scope([_result(0.79, False)], SCOPE_THRESHOLD)
    assert status == "in_scope"
    assert len(shown) == 1


def test_related_but_weak_query_reports_no_evidence():
    status, _, shown = classify_scope([_result(0.60, True)], SCOPE_THRESHOLD)
    assert status == "no_evidence"
    assert len(shown) == 1
