"""Cross-Encoder Reranking module with graceful fallback (Day 2).

If the cross-encoder model fails to load or raises at inference time, the
module falls back to normalised step-decay scoring so the system never
crashes — Constitution Principle: Fail-Safe Fallback.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Sequence
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.monitoring import trace_span

logger = logging.getLogger(__name__)


def sigmoid(x: float) -> float:
    """Calibrate logits to [0, 1] range."""
    return 1.0 / (1.0 + math.exp(-x))


_MODEL_CACHE: dict[str, Any] = {}

# The cross-encoder truncates each pair to 512 tokens anyway (its own
# tokenizer max_length), but sentence-transformers pads every pair in a batch
# to the LONGEST sequence in that batch. One oversized chunk -- this corpus
# keeps a numbered recommendation whole and unsplit even past the target size
# (chunker.py) -- was dragging every other candidate in its batch up to ~512
# padded tokens too, turning a ~10ms/pair score into ~70ms/pair. Trimming the
# text we hand the tokenizer keeps the same information (it would have been
# truncated at the same point regardless) while keeping the batch's padded
# length bounded and cheap.
_MAX_RERANK_CHARS = 1800  # ~450 tokens: leaves room for the query + template.


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

    def _get_model(self):
        if self._disabled:
            return None
        if self._model_name not in _MODEL_CACHE:
            try:
                from sentence_transformers import CrossEncoder

                logger.info("Loading CrossEncoder model '%s'...", self._model_name)
                started = time.perf_counter()
                _MODEL_CACHE[self._model_name] = CrossEncoder(self._model_name)
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "CrossEncoder loaded in %.0f ms: %s",
                    elapsed_ms,
                    self._model_name,
                    extra={
                        "event": "rerank.model_load",
                        "model": self._model_name,
                        "duration_ms": round(elapsed_ms, 2),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Could not initialise CrossEncoder reranker model '%s': %s. "
                    "Falling back to rank fusion.",
                    self._model_name,
                    exc,
                )
                _MODEL_CACHE[self._model_name] = None
        return _MODEL_CACHE.get(self._model_name)

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
        with trace_span(op="rag.reranker.rerank", description="CrossEncoder Rerank"):
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
                    started = time.perf_counter()
                    pairs = [
                        [query, f"{c.section_title}: {c.text[:_MAX_RERANK_CHARS]}"]
                        for c in extracted_chunks
                    ]
                    scores = model.predict(pairs, show_progress_bar=False)
                    norm_scores = [sigmoid(float(s)) for s in scores]
                    ranked = sorted(
                        zip(extracted_chunks, norm_scores, strict=False),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    logger.debug(
                        "rerank scored %d pairs in %.1f ms (top=%.4f)",
                        len(pairs),
                        elapsed_ms,
                        ranked[0][1] if ranked else 0.0,
                        extra={
                            "event": "rerank.scored",
                            "model": self._model_name,
                            "pairs": len(pairs),
                            "duration_ms": round(elapsed_ms, 2),
                            "ms_per_pair": round(elapsed_ms / max(1, len(pairs)), 3),
                            "top_score": round(ranked[0][1], 4) if ranked else 0.0,
                            "min_score": round(min(norm_scores), 4) if norm_scores else 0.0,
                        },
                    )
                    return list(ranked)[:k]
                except Exception as exc:
                    logger.error(
                        "CrossEncoder reranking failed at runtime: %s. Using fallback ordering.",
                        exc,
                        extra={
                            "event": "rerank.failed",
                            "model": self._model_name,
                            "candidates": len(extracted_chunks),
                        },
                    )

            # Fallback: preserve input order with uniform step-decay scores.
            # Logged at WARNING because relevance is now fusion order, not
            # cross-encoder relevance -- scores below are not comparable.
            logger.warning(
                "rerank falling back to step-decay ordering for %d candidates.",
                len(extracted_chunks),
                extra={
                    "event": "rerank.fallback",
                    "model": self._model_name,
                    "candidates": len(extracted_chunks),
                    "disabled": self._disabled,
                },
            )
            n = len(extracted_chunks)
            fallback = [
                (c, max(0.1, 1.0 - (i / max(1, n)))) for i, c in enumerate(extracted_chunks)
            ]
            return fallback[:k]
