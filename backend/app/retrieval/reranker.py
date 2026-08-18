"""Cross-Encoder Reranking module with graceful fallback (Day 2).

If the cross-encoder model fails to load or raises at inference time, the
module falls back to normalised step-decay scoring so the system never
crashes — Constitution Principle: Fail-Safe Fallback.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult

logger = logging.getLogger(__name__)


def sigmoid(x: float) -> float:
    """Calibrate logits to [0, 1] range."""
    return 1.0 / (1.0 + math.exp(-x))


class CrossEncoderReranker:
    """Reranks candidate chunks using a cross-attention transformer model."""

    def __init__(
        self,
        settings: Settings | None = None,
        model_name: str | None = None,
        disabled: bool = False,
    ) -> None:
        self._settings = settings or get_settings()
        self._model_name = model_name or self._settings.reranker_model
        self._disabled = disabled
        self._model = None
        self._load_attempted = False

    def _get_model(self):
        if self._disabled:
            return None
        if not self._load_attempted:
            self._load_attempted = True
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_name)
                logger.info("CrossEncoder loaded successfully: %s", self._model_name)
            except Exception as exc:
                logger.warning(
                    "Could not initialise CrossEncoder reranker model '%s': %s. "
                    "Falling back to rank fusion.",
                    self._model_name,
                    exc,
                )
                self._model = None
        return self._model

    @property
    def is_available(self) -> bool:
        """True when the cross-encoder model was loaded successfully."""
        return self._get_model() is not None

    def rerank(
        self,
        query: str,
        chunks: Sequence[Chunk | RetrievalResult],
        top_k: int | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Score and re-sort *chunks* by relevance to *query*.

        Returns a list of ``(Chunk, score)`` pairs sorted best-first.
        Scores are normalized to [0, 1] via sigmoid calibration.
        On any error the input order is preserved with step-decay scoring.
        """
        if not chunks:
            return []

        # Extract Chunk objects if RetrievalResult instances were passed
        extracted_chunks: list[Chunk] = [
            item.chunk if isinstance(item, RetrievalResult) else item for item in chunks
        ]

        k = top_k or len(extracted_chunks)
        model = self._get_model()

        if model is not None:
            try:
                pairs = [[query, f"{c.section_title}: {c.text}"] for c in extracted_chunks]
                scores = model.predict(pairs)
                norm_scores = [sigmoid(float(s)) for s in scores]
                ranked = sorted(
                    zip(extracted_chunks, norm_scores, strict=False),
                    key=lambda x: x[1],
                    reverse=True,
                )
                return list(ranked)[:k]
            except Exception as exc:
                logger.error(
                    "CrossEncoder reranking failed at runtime: %s. Using fallback ordering.",
                    exc,
                )

        # Fallback: preserve input order with uniform step-decay scores.
        n = len(extracted_chunks)
        fallback = [(c, max(0.1, 1.0 - (i / max(1, n)))) for i, c in enumerate(extracted_chunks)]
        return fallback[:k]
