"""Cross-Encoder Reranking module with graceful fallback (Day 2).

If the cross-encoder model fails to load or raises at inference time, the
module falls back to normalised step-decay scoring so the system never
crashes — Constitution Principle: Fail-Safe Fallback.
"""

from __future__ import annotations

import logging
from typing import Sequence

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks candidate chunks using a cross-attention model.

    Parameters
    ----------
    settings : Settings | None
        Application settings (provides ``reranker_model``).
    disabled : bool
        If *True*, skip model loading entirely and always use the fallback.
        Useful for unit tests and environments without GPU/weights.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        disabled: bool = False,
    ) -> None:
        self._settings = settings or get_settings()
        self._model = None
        self._disabled = disabled

        if not self._disabled:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._settings.reranker_model)
                logger.info(
                    "CrossEncoder reranker loaded: %s",
                    self._settings.reranker_model,
                )
            except Exception as exc:
                logger.warning(
                    "Could not initialise CrossEncoder reranker model '%s': %s. "
                    "Falling back to rank fusion.",
                    self._settings.reranker_model,
                    exc,
                )
                self._model = None

    @property
    def is_available(self) -> bool:
        """True when the cross-encoder model was loaded successfully."""
        return self._model is not None

    def rerank(
        self, query: str, chunks: Sequence[Chunk]
    ) -> list[tuple[Chunk, float]]:
        """Score and re-sort *chunks* by relevance to *query*.

        Returns a list of ``(Chunk, score)`` pairs sorted best-first.
        Scores are normalised to [0, 1].  On any error the input order
        is preserved with a uniform step-decay score — no crash.
        """
        if not chunks:
            return []

        if self._model is not None:
            try:
                pairs = [[query, c.text] for c in chunks]
                scores = self._model.predict(pairs)
                min_s = float(min(scores))
                max_s = float(max(scores))
                denom = (max_s - min_s) if max_s > min_s else 1.0
                norm_scores = [(float(s) - min_s) / denom for s in scores]
                ranked = sorted(
                    zip(chunks, norm_scores), key=lambda x: x[1], reverse=True
                )
                return list(ranked)
            except Exception as exc:
                logger.error(
                    "CrossEncoder reranking failed at runtime: %s. "
                    "Using fallback ordering.",
                    exc,
                )

        # Fallback: preserve input order with uniform step-decay scores.
        n = len(chunks)
        return [(c, max(0.1, 1.0 - (i / max(1, n)))) for i, c in enumerate(chunks)]
