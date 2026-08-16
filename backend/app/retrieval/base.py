"""Retriever protocol — the Day 2 substitution seam (FR-035).

Day 1 ships dense cosine top-K only. Hybrid BM25+dense and cross-encoder reranking
are Day 2 work, and this protocol is what lets them drop in without the API layer
noticing (research.md D7).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.models import RetrievalResult


@runtime_checkable
class Retriever(Protocol):
    def search(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Return up to `top_k` results, ranked best-first.

        Implementations MUST NOT drop low-scoring results. Weak matches are
        returned with `below_floor=True` so failure modes stay observable
        (Constitution Principle VI, FR-023).
        """
        ...
