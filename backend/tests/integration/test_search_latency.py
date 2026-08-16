"""Search latency check (T049, SC-007): each search under 3 seconds end to end."""

from __future__ import annotations

import statistics
import time

import pytest

from backend.app.config import get_settings
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.store import VectorStore

BUDGET_SECONDS = 3.0
RUNS = 10

QUERIES = [
    "What are the symptoms of adrenal insufficiency?",
    "How should an adrenal crisis be managed?",
    "What is sick-day dosing?",
    "Which glucocorticoid is recommended for adults?",
    "When should someone be referred to an endocrinologist?",
]


@pytest.fixture(scope="module")
def timings():
    settings = get_settings()
    store = VectorStore(settings)

    if not store.is_ready():
        pytest.skip("No index built. Run: python -m backend.app.cli ingest")
    if not settings.openrouter_api_key:
        pytest.skip("No API key configured; search must embed the query.")

    retriever = DenseRetriever(store=store, settings=settings)
    retriever.search("warm up the connection", 1)  # exclude cold-start cost

    measured: list[float] = []
    for i in range(RUNS):
        query = QUERIES[i % len(QUERIES)]
        started = time.perf_counter()
        retriever.search(query, settings.top_k)
        measured.append(time.perf_counter() - started)

    print(
        f"\nSearch latency over {RUNS} runs — "
        f"mean {statistics.mean(measured):.2f}s | "
        f"median {statistics.median(measured):.2f}s | "
        f"max {max(measured):.2f}s | budget {BUDGET_SECONDS:.0f}s"
    )
    return measured


class TestSearchLatency:
    def test_every_search_is_within_budget(self, timings):
        slow = [round(t, 2) for t in timings if t > BUDGET_SECONDS]
        assert not slow, f"searches exceeded {BUDGET_SECONDS}s: {slow}"

    def test_median_has_headroom(self, timings):
        assert statistics.median(timings) < BUDGET_SECONDS * 0.8
