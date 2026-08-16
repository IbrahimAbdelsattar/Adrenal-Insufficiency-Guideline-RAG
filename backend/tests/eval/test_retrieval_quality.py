"""Golden-set retrieval quality regression test (T038, FR-032, FR-033, SC-003).

Requires a built index and a reachable embedding gateway; skipped otherwise so the
rest of the suite stays runnable offline.
"""

from __future__ import annotations

import pytest

from backend.app.config import get_settings
from backend.app.evaluation import (
    TARGET_HIT_RATE,
    evaluate,
    load_golden_questions,
)
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.store import VectorStore


@pytest.fixture(scope="module")
def report():
    settings = get_settings()
    store = VectorStore(settings)

    if not store.is_ready():
        pytest.skip("No index built. Run: python -m backend.app.cli ingest")
    if not settings.openrouter_api_key:
        pytest.skip("No API key configured; retrieval needs to embed the query.")

    retriever = DenseRetriever(store=store, settings=settings)
    result = evaluate(retriever, settings=settings)

    # Printed so a failing run shows which questions regressed.
    print(f"\nGolden set: {result.total} questions | top_k={result.top_k}\n")
    for outcome in result.outcomes:
        rank = f"rank {outcome.rank}" if outcome.rank else "--"
        print(
            f"  {outcome.question.id}  {outcome.status:<4}  {rank:<8}"
            f"expected {','.join(outcome.question.expected_sections):<9}"
            f"{outcome.question.question[:44]}"
        )
    print(
        f"\nHit rate: {result.hits}/{result.total} ({result.hit_rate:.1%})   "
        f"target >= {TARGET_HIT_RATE:.0%}   "
        f"{'PASS' if result.passed else 'FAIL'}"
    )
    if result.hits:
        print(f"Mean rank of hits: {result.mean_hit_rank:.1f}")

    return result


class TestGoldenSetIntegrity:
    """These run without an index — they validate the fixture itself."""

    def test_at_least_ten_questions(self):
        assert len(load_golden_questions()) >= 10  # FR-031

    def test_every_question_declares_an_expected_section(self):
        assert all(q.expected_sections for q in load_golden_questions())

    def test_question_ids_are_unique(self):
        ids = [q.id for q in load_golden_questions()]
        assert len(ids) == len(set(ids))

    def test_every_question_targets_a_registered_document(self):
        from backend.app.ingestion.registry import load_registry

        registered = {d.doc_id for d in load_registry()}
        for question in load_golden_questions():
            assert question.expected_doc_id in registered


class TestRetrievalQuality:
    def test_hit_rate_meets_target(self, report):
        """SC-003: >= 80% of questions retrieve their expected section in top-K."""
        assert report.hit_rate >= TARGET_HIT_RATE, (
            f"Hit rate {report.hit_rate:.1%} below target {TARGET_HIT_RATE:.0%}. "
            f"Missed: {[o.question.id for o in report.misses]}"
        )

    def test_every_question_returns_something(self, report):
        assert all(o.retrieved_sections for o in report.outcomes)

    def test_hits_rank_highly(self, report):
        """A hit buried at rank 5 is barely a hit; the mean should be near the top."""
        assert report.mean_hit_rank <= 3.0
