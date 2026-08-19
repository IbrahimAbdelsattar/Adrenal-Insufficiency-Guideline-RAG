"""Fallback and resilient embedding provider.

Wraps a primary remote embedder (e.g. Gemini via OpenRouter/OmniRoute) with a local
SentenceTransformer fallback (e.g. BAAI/bge-small-en-v1.5) to ensure uninterrupted
vector retrieval and ingestion even during network degradation or upstream API outages.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.embeddings.local import LocalEmbedder
from backend.app.errors import ConfigurationError, EmbeddingProviderError

logger = logging.getLogger(__name__)


class FallbackEmbedder:
    """Resilient embedder that routes to local fallback when the primary provider fails."""

    def __init__(
        self,
        settings: Settings | None = None,
        primary: Embedder | None = None,
        secondary: Embedder | None = None,
        fallback_enabled: bool | None = None,
    ) -> None:
        if isinstance(settings, Embedder) and not isinstance(settings, Settings):
            primary, settings = settings, None
        self._settings = settings or get_settings()
        self._primary = primary
        self._secondary = secondary
        self._fallback_enabled = (
            fallback_enabled
            if fallback_enabled is not None
            else self._settings.enable_embedding_fallback
        )
        self._is_fallback_active = False
        self._primary_failure_reason: str | None = None

    @property
    def primary(self) -> Embedder:
        if self._primary is None:
            from backend.app.embeddings.openrouter import OpenRouterEmbedder

            try:
                self._primary = OpenRouterEmbedder(self._settings)
            except ConfigurationError as exc:
                if self._fallback_enabled:
                    logger.warning(
                        "Primary embedder configuration unavailable (%s). Activating local fallback embedder.",
                        exc,
                        extra={
                            "event": "embedding.fallback.init_fallback",
                            "reason": str(exc),
                        },
                    )
                    self._is_fallback_active = True
                    self._primary_failure_reason = str(exc)
                else:
                    raise
        return self._primary

    @property
    def secondary(self) -> Embedder:
        if self._secondary is None:
            self._secondary = LocalEmbedder(self._settings)
        return self._secondary

    @property
    def is_fallback_active(self) -> bool:
        """True if the system has failed over to the local fallback embedder."""
        return self._is_fallback_active

    @property
    def active_embedder(self) -> Embedder:
        """The embedder currently handling requests."""
        if self._is_fallback_active:
            return self.secondary
        try:
            return self.primary
        except Exception:
            if self._fallback_enabled:
                self._is_fallback_active = True
                return self.secondary
            raise

    @property
    def model_id(self) -> str:
        return self.active_embedder.model_id

    @property
    def dimensions(self) -> int:
        return self.active_embedder.dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._fallback_enabled:
            return self.primary.embed_documents(texts)

        if self._is_fallback_active:
            return self.secondary.embed_documents(texts)

        started = time.perf_counter()
        try:
            return self.primary.embed_documents(texts)
        except Exception as exc:
            self._is_fallback_active = True
            self._primary_failure_reason = str(exc)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "Primary embedder failed on documents after %.0f ms (%s). Falling back to %s",
                elapsed_ms,
                exc,
                self.secondary.model_id,
                extra={
                    "event": "embedding.fallback.triggered",
                    "operation": "embed_documents",
                    "documents": len(texts),
                    "primary_model": getattr(self._primary, "model_id", self._settings.embedding_model),
                    "fallback_model": self.secondary.model_id,
                    "error": str(exc),
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
            return self.secondary.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self._fallback_enabled:
            return self.primary.embed_query(text)

        if self._is_fallback_active:
            return self.secondary.embed_query(text)

        started = time.perf_counter()
        try:
            return self.primary.embed_query(text)
        except Exception as exc:
            self._is_fallback_active = True
            self._primary_failure_reason = str(exc)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "Primary embedder failed on query after %.0f ms (%s). Falling back to %s",
                elapsed_ms,
                exc,
                self.secondary.model_id,
                extra={
                    "event": "embedding.fallback.triggered",
                    "operation": "embed_query",
                    "primary_model": getattr(self._primary, "model_id", self._settings.embedding_model),
                    "fallback_model": self.secondary.model_id,
                    "error": str(exc),
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
            return self.secondary.embed_query(text)
