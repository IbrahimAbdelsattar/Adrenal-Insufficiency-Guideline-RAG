"""Scope classification (in_scope / no_evidence / out_of_scope)."""

from __future__ import annotations

import pytest

from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.scope import classify_scope

THRESHOLD = 0.005


def _result(score: float, *, below_floor: bool, rank: int = 1) -> RetrievalResult:
    chunk = Chunk(
        chunk_id=f"chunk_0{rank}",
        text="Adrenal insufficiency guidance.",
        document_name="NICE NG243",
        doc_id="nice_ng243",
        source_url="https://nice.org.uk/ng243",
        document_type="guideline",
        publication_year=2024,
        requires_caution=False,
        page_number=1,
        section_number="1.1",
        section_title="1.1 Identification",
    )
    return RetrievalResult(
        chunk=chunk, score=score, rank=rank, below_floor=below_floor
    )


def test_strong_match_is_in_scope_and_keeps_results():
    results = [_result(0.99, below_floor=False)]

    status, message, shown = classify_scope(results, THRESHOLD)

    assert status == "in_scope"
    assert shown == results
    assert message


def test_unrelated_query_is_out_of_scope_and_suppresses_results():
    # The bug this guards: asking an unrelated question must not surface
    # glucocorticoid withdrawal text as if it were an answer.
    results = [_result(0.0, below_floor=True)]

    status, _, shown = classify_scope(results, THRESHOLD)

    assert status == "out_of_scope"
    assert shown == []


def test_related_but_weak_is_no_evidence_and_keeps_results():
    # Above the scope threshold but nothing above the evidence floor. These
    # results are still shown, so a clinician is not told a relevant question
    # is off-topic.
    results = [_result(0.110, below_floor=True)]

    status, _, shown = classify_scope(results, THRESHOLD)

    assert status == "no_evidence"
    assert shown == results


def test_empty_results_are_out_of_scope():
    status, _, shown = classify_scope([], THRESHOLD)

    assert status == "out_of_scope"
    assert shown == []


@pytest.mark.parametrize(
    ("top_score", "expected"),
    [
        (0.0, "out_of_scope"),
        (0.004, "out_of_scope"),
        (0.005, "no_evidence"),  # boundary is inclusive
        (0.007, "no_evidence"),
    ],
)
def test_threshold_boundary(top_score, expected):
    results = [_result(top_score, below_floor=True)]

    status, _, _ = classify_scope(results, THRESHOLD)

    assert status == expected


def test_evidence_above_floor_wins_even_when_later_results_are_weak():
    results = [
        _result(0.99, below_floor=False, rank=1),
        _result(0.01, below_floor=True, rank=2),
    ]

    status, _, shown = classify_scope(results, THRESHOLD)

    assert status == "in_scope"
    assert len(shown) == 2
