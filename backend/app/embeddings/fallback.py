"""Fallback and resilient embedding provider.

Wraps a primary remote embedder (e.g. Gemini via OpenRouter/OmniRoute) with a local
SentenceTransformer fallback (e.g. BAAI/bge-small-en-v1.5) to ensure uninterrupted
vector retrieval and ingestion even during network degradation or upstream API outages.
"""

from __future__ import annotations

import json
import logging
import time

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.embeddings.local import LocalEmbedder
from backend.app.errors import ConfigurationError

logger = logging.getLogger(__name__)


def index_embedding_model(settings: Settings) -> str | None:
    """The embedding model that actually built the current index, per its manifest.

    Returns None when no readable manifest exists (nothing has been ingested yet).
    """
    path = settings.manifest_path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("embedding_model")
    except Exception:
        return None


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
        # None = not yet resolved; see `_query_pinned_to_local`.
        self._pin_query_to_local: bool | None = None

    @property
    def _query_pinned_to_local(self) -> bool:
        """True when the live index was built by the local model, so queries must use it too.

        A query vector only means anything against an index built by the *same*
        model: mixing them either raises a dimension mismatch (384 vs 3072) or,
        worse, silently returns garbage neighbours at a matching width. When the
        manifest says the index is local, calling the remote provider is doomed
        no matter whether it is up -- so skip it and save the round trip.

        Deliberately scoped to queries. `embed_documents` stays free to reach for
        the primary provider, because ingestion *defines* a new index rather than
        having to match the existing one.
        """
        if self._pin_query_to_local is None:
            built_with = index_embedding_model(self._settings)
            local_model = self._settings.local_embedding_model
            self._pin_query_to_local = bool(
                self._fallback_enabled
                and built_with
                and built_with == local_model
                and built_with != self._settings.embedding_model
            )
            if self._pin_query_to_local:
                logger.info(
                    "Index was built with the local model '%s'; pinning query embeddings "
                    "to it and skipping the remote provider '%s'.",
                    local_model,
                    self._settings.embedding_model,
                    extra={
                        "event": "embedding.query_pinned_local",
                        "index_model": built_with,
                        "configured_primary": self._settings.embedding_model,
                    },
                )
        return self._pin_query_to_local

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
        """True if the local embedder is serving queries -- by failover or by index pin."""
        return self._is_fallback_active or self._query_pinned_to_local

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
                    "primary_model": getattr(
                        self._primary, "model_id", self._settings.embedding_model
                    ),
                    "fallback_model": self.secondary.model_id,
                    "error": str(exc),
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
            return self.secondary.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self._fallback_enabled:
            return self.primary.embed_query(text)

        if self._is_fallback_active or self._query_pinned_to_local:
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
                    "primary_model": getattr(
                        self._primary, "model_id", self._settings.embedding_model
                    ),
                    "fallback_model": self.secondary.model_id,
                    "error": str(exc),
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
            return self.secondary.embed_query(text)
