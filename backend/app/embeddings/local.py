"""Local embeddings provider using SentenceTransformers.

Provides a fast, zero-network, local embedding model (e.g. BAAI/bge-small-en-v1.5)
to serve as an offline or high-availability fallback when remote APIs are unavailable.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.errors import EmbeddingProviderError
from backend.app.retrieval.cache import TTLLRUCache, normalize_query

logger = logging.getLogger(__name__)

_LOCAL_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


class LocalEmbedder:
    """Local embedding generator backed by SentenceTransformers."""

    def __init__(
        self,
        settings: Settings | None = None,
        model_name: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._model_name = model_name or self._settings.local_embedding_model
        self._dimensions = 0
        self._query_cache: TTLLRUCache[str, list[float]] = TTLLRUCache(
            maxsize=self._settings.embedding_cache_size,
            ttl_seconds=self._settings.cache_ttl_seconds,
            manifest_path=self._settings.index_dir / "manifest.json",
            name="local_embedding_cache",
        )

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        if not self._dimensions:
            model = self._get_model()
            dim = getattr(model, "get_embedding_dimension", None) or getattr(
                model, "get_sentence_embedding_dimension", None
            )
            if callable(dim):
                self._dimensions = int(dim())
        return self._dimensions

    def _get_model(self) -> Any:
        if self._model_name not in _LOCAL_MODEL_CACHE:
            with _MODEL_LOCK:
                if self._model_name not in _LOCAL_MODEL_CACHE:
                    try:
                        from sentence_transformers import SentenceTransformer

                        logger.info(
                            "Loading local SentenceTransformer model '%s'...", self._model_name
                        )
                        started = time.perf_counter()
                        # Try the local HF cache first. Even with the weights
                        # already downloaded, SentenceTransformer revalidates
                        # every file against the Hub, which dominates load time
                        # (~20s of HEAD/GET round trips here) and makes startup
                        # depend on huggingface.co being reachable. Fall back to
                        # a networked load only if the cache cannot satisfy it.
                        try:
                            model = SentenceTransformer(self._model_name, local_files_only=True)
                        except Exception:
                            logger.info(
                                "Local cache miss for '%s'; downloading from the HF Hub.",
                                self._model_name,
                                extra={
                                    "event": "embedding.local.cache_miss",
                                    "model": self._model_name,
                                },
                            )
                            model = SentenceTransformer(self._model_name)
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        _LOCAL_MODEL_CACHE[self._model_name] = model

                        dim = getattr(model, "get_embedding_dimension", None) or getattr(
                            model, "get_sentence_embedding_dimension", None
                        )
                        if callable(dim):
                            self._dimensions = int(dim())

                        logger.info(
                            "Local SentenceTransformer '%s' loaded in %.0f ms (dims=%d)",
                            self._model_name,
                            elapsed_ms,
                            self._dimensions,
                            extra={
                                "event": "embedding.local.model_load",
                                "model": self._model_name,
                                "dimensions": self._dimensions,
                                "duration_ms": round(elapsed_ms, 2),
                            },
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to load local SentenceTransformer model '%s': %s",
                            self._model_name,
                            exc,
                            extra={
                                "event": "embedding.local.load_failed",
                                "model": self._model_name,
                                "error": str(exc),
                            },
                        )
                        raise EmbeddingProviderError(
                            f"Could not load local embedding model '{self._model_name}': {exc}"
                        ) from exc
        return _LOCAL_MODEL_CACHE[self._model_name]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        batch_size = max(1, self._settings.embedding_batch_size)
        started = time.perf_counter()

        try:
            raw_embeddings = model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            vectors: list[list[float]] = (
                raw_embeddings.tolist()
                if hasattr(raw_embeddings, "tolist")
                else [list(map(float, vec)) for vec in raw_embeddings]
            )
        except Exception as exc:
            logger.error(
                "Local embedding generation failed for %d documents: %s",
                len(texts),
                exc,
                extra={
                    "event": "embedding.local.documents_failed",
                    "model": self._model_name,
                    "documents": len(texts),
                    "error": str(exc),
                },
            )
            raise EmbeddingProviderError(
                f"Local embedding failed on documents (model={self._model_name}): {exc}"
            ) from exc

        if vectors and not self._dimensions:
            self._dimensions = len(vectors[0])

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Local embedded %d documents in %.0f ms (%.1f ms/doc)",
            len(texts),
            elapsed_ms,
            elapsed_ms / max(1, len(texts)),
            extra={
                "event": "embedding.local.documents",
                "model": self.model_id,
                "documents": len(texts),
                "dimensions": self._dimensions,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        key = normalize_query(text)
        cached = self._query_cache.get(key)
        if cached is not None:
            logger.debug(
                "Local embedding cache hit (cached_queries=%d)",
                len(self._query_cache),
                extra={
                    "event": "embedding.local.query",
                    "cache_hit": True,
                    "model": self.model_id,
                    "duration_ms": 0.0,
                    "cached_queries": len(self._query_cache),
                },
            )
            return cached

        model = self._get_model()
        started = time.perf_counter()
        try:
            raw_embedding = model.encode(
                [text],
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            vec: list[float] = (
                raw_embedding[0].tolist()
                if hasattr(raw_embedding, "tolist")
                else list(map(float, raw_embedding[0]))
            )
        except Exception as exc:
            logger.error(
                "Local embedding generation failed for query: %s",
                exc,
                extra={
                    "event": "embedding.local.query_failed",
                    "model": self._model_name,
                    "error": str(exc),
                },
            )
            raise EmbeddingProviderError(
                f"Local embedding failed for query (model={self._model_name}): {exc}"
            ) from exc

        if not self._dimensions:
            self._dimensions = len(vec)

        self._query_cache.put(key, vec)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Local embedded query in %.0f ms (model=%s dims=%d)",
            elapsed_ms,
            self.model_id,
            len(vec),
            extra={
                "event": "embedding.local.query",
                "cache_hit": False,
                "model": self.model_id,
                "dimensions": len(vec),
                "duration_ms": round(elapsed_ms, 2),
                "cached_queries": len(self._query_cache),
            },
        )
        return vec
