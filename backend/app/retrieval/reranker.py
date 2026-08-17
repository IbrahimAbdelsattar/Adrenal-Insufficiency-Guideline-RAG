"""Cross-Encoder Reranker (Day 2 Lab, Advanced Retrieval).

Re-scores top candidate chunks from dual retrieval (Dense + BM25) using cross-attention.
Preserves all provenance citations and constitutional below_floor flags.
Gracefully falls back to incoming ranking if weights are unavailable offline.
"""

from __future__ import annotations

import logging
from typing import Sequence

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-x))


class CrossEncoderReranker:
    """Reranks candidate (query, chunk) pairs using a cross-attention transformer."""

    def __init__(
        self,
        model_name: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._model_name = model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        self._model = None
        self._load_attempted = False

    def _get_model(self):
        if not self._load_attempted:
            self._load_attempted = True
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_name)
                logger.info("CrossEncoder loaded successfully: %s", self._model_name)
            except Exception as exc:
                logger.warning(
                    "CrossEncoder '%s' could not be loaded (%s); using fallback score pass-through.",
                    self._model_name,
                    exc,
                )
                self._model = None
        return self._model

    def rerank(
        self,
        query: str,
        results: Sequence[RetrievalResult],
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Rerank candidates and return top_k calibrated results."""
        if not results:
            return []

        k = top_k or len(results)
        floor = self._settings.relevance_floor
        model = self._get_model()

        if model is None:
            # Graceful fallback: return top_k candidates with existing scores
            return list(results)[:k]

        pairs = [[query, f"{r.chunk.section_title}: {r.chunk.text}"] for r in results]
        try:
            raw_scores = model.predict(pairs)
            calibrated_scores = [_sigmoid(float(s)) for s in raw_scores]

            # Re-sort by cross-encoder score descending
            ranked_indices = sorted(
                range(len(results)), key=lambda i: calibrated_scores[i], reverse=True
            )[:k]

            reranked: list[RetrievalResult] = []
            for rank, idx in enumerate(ranked_indices, start=1):
                chunk = results[idx].chunk
                score = calibrated_scores[idx]
                reranked.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=score,
                        rank=rank,
                        below_floor=score < floor,
                    )
                )
            return reranked
        except Exception as exc:
            logger.warning("Error during reranking (%s); falling back to candidate order.", exc)
            return list(results)[:k]
