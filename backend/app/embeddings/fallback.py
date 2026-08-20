"""Fallback and resilient embedding provider.

Wraps a primary remote embedder (e.g. Gemini via OpenRouter/OmniRoute) with a local
SentenceTransformer fallback (e.g. BAAI/bge-small-en-v1.5) to ensure uninterrupted
vector retrieval and ingestion even during network degradation or upstream API outages.
"""

from __future__ import annotations

import logging

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
            self._primary = LocalEmbedder(
                self._settings, model_name=self._settings.local_embedding_model
            )
        return self._primary

    @property
    def secondary(self) -> Embedder:
        if self._secondary is None:
            from backend.app.embeddings.openrouter import OpenRouterEmbedder

            try:
                self._secondary = OpenRouterEmbedder(
                    self._settings, model_name=self._settings.remote_embedding_model
                )
            except ConfigurationError as exc:
                if self._fallback_enabled:
                    logger.warning(
                        "Remote secondary embedder unavailable (%s). Continuing with primary local embedder.",
                        exc,
                        extra={
                            "event": "embedding.fallback.init_secondary_unavailable",
                            "reason": str(exc),
                        },
                    )
                    self._secondary = None
                else:
                    raise
        return self._secondary

    @property
    def fallback(self) -> Embedder:
        """Alias for secondary embedder."""
        return self.secondary

    @property
    def is_fallback_active(self) -> bool:
        """True if the remote fallback embedder has taken over from the local primary."""
        return self._is_fallback_active

    @property
    def active_embedder(self) -> Embedder:
        """The embedder currently handling requests."""
        if self.is_fallback_active:
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

        if not self._fallback_enabled or not self._is_fallback_active:
            try:
                return self.primary.embed_documents(texts)
            except Exception as exc:
                if not self._fallback_enabled:
                    raise
                self._is_fallback_active = True
                self._primary_failure_reason = str(exc)
                logger.warning(
                    "Primary embedder failed on documents (%s). Falling back to secondary.",
                    exc,
                )

        if self.secondary is not None:
            return self.secondary.embed_documents(texts)
        raise EmbeddingProviderError(f"Primary embedder failed: {self._primary_failure_reason}")

    def embed_query(self, text: str) -> list[float]:
        if not self._fallback_enabled or not self._is_fallback_active:
            try:
                return self.primary.embed_query(text)
            except Exception as exc:
                if not self._fallback_enabled:
                    raise
                self._is_fallback_active = True
                self._primary_failure_reason = str(exc)
                logger.warning(
                    "Primary embedder failed on query (%s). Falling back to secondary.",
                    exc,
                )

        if self.secondary is not None:
            return self.secondary.embed_query(text)
        raise EmbeddingProviderError(
            f"Primary embedder failed: {self._primary_reason if hasattr(self, '_primary_reason') else self._primary_failure_reason}"
        )
