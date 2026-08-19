"""OpenRouter embeddings client.

OpenRouter exposes an OpenAI-compatible POST /embeddings endpoint, so one API key
covers embeddings today and generation on Day 2 (research.md D3).
"""

from __future__ import annotations

import logging
import time

import httpx

from backend.app.config import Settings, get_settings
from backend.app.errors import ConfigurationError, EmbeddingProviderError
from backend.app.retrieval.cache import TTLLRUCache, normalize_query

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 120.0
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenRouterEmbedder:
    """Batched embeddings with retry on rate limits and transient server errors."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openrouter_api_key:
            raise ConfigurationError(
                "OMNIROUTE_API_KEY is not set — the OmniRoute gateway key is "
                "required to embed queries. Set it in your deployment platform's "
                "environment settings, or locally copy .env.example to .env and "
                "add it. (The legacy name OPENROUTER_API_KEY is also accepted.)"
            )
        self._dimensions = 0
        self._query_cache: TTLLRUCache[str, list[float]] = TTLLRUCache(
            maxsize=self._settings.embedding_cache_size,
            ttl_seconds=self._settings.cache_ttl_seconds,
            manifest_path=self._settings.index_dir / "manifest.json",
            name="embedding_cache",
        )

    @property
    def model_id(self) -> str:
        return self._settings.embedding_model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    # ------------------------------------------------------------------

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = max(1, self._settings.embedding_batch_size)
        vectors: list[list[float]] = []
        started = time.perf_counter()
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                vectors.extend(self._embed_batch(client, batch))

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Embedded %d documents in %d batches in %.0f ms (%.1f ms/doc)",
            len(texts),
            (len(texts) + batch_size - 1) // batch_size,
            elapsed_ms,
            elapsed_ms / max(1, len(texts)),
            extra={
                "event": "embedding.documents",
                "model": self.model_id,
                "documents": len(texts),
                "batches": (len(texts) + batch_size - 1) // batch_size,
                "batch_size": batch_size,
                "dimensions": self._dimensions,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        # The cache turns a repeat query into a zero-latency lookup; logging
        # the hit is what makes a suspiciously fast retrieval explainable.
        key = normalize_query(text)
        cached = self._query_cache.get(key)
        if cached is not None:
            logger.debug(
                "Embedding cache hit (cached_queries=%d)",
                len(self._query_cache),
                extra={
                    "event": "embedding.query",
                    "cache_hit": True,
                    "model": self.model_id,
                    "duration_ms": 0.0,
                    "cached_queries": len(self._query_cache),
                },
            )
            return cached

        started = time.perf_counter()
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            vec = self._embed_batch(client, [text])[0]
            self._query_cache.put(key, vec)

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Embedded query in %.0f ms (model=%s dims=%d)",
            elapsed_ms,
            self.model_id,
            len(vec),
            extra={
                "event": "embedding.query",
                "cache_hit": False,
                "model": self.model_id,
                "dimensions": len(vec),
                "duration_ms": round(elapsed_ms, 2),
                "cached_queries": len(self._query_cache),
            },
        )
        return vec


    # ------------------------------------------------------------------

    def _embed_batch(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        url = f"{self._settings.openrouter_base_url.rstrip('/')}/embeddings"
        payload = {"model": self.model_id, "input": batch}
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        last_error = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempt_started = time.perf_counter()
            try:
                response = client.post(url, json=payload, headers=headers)
            except httpx.RequestError as exc:
                last_error = f"network error: {exc}"
            else:
                if response.status_code == 200:
                    logger.debug(
                        "embedding.batch ok inputs=%d attempt=%d in %.0f ms",
                        len(batch),
                        attempt,
                        (time.perf_counter() - attempt_started) * 1000,
                        extra={
                            "event": "embedding.batch",
                            "model": self.model_id,
                            "inputs": len(batch),
                            "attempt": attempt,
                            "duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                        },
                    )
                    return self._parse(response.json(), expected=len(batch))
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code not in RETRY_STATUS:
                    break

            logger.warning(
                "Embedding attempt %d/%d failed: %s",
                attempt,
                MAX_ATTEMPTS,
                last_error,
                extra={
                    "event": "embedding.retry",
                    "model": self.model_id,
                    "attempt": attempt,
                    "max_attempts": MAX_ATTEMPTS,
                    "inputs": len(batch),
                    "error": last_error,
                },
            )

            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_BASE_SECONDS**attempt)

        logger.error(
            "Embedding request exhausted %d attempts (model=%s): %s",
            MAX_ATTEMPTS,
            self.model_id,
            last_error,
            extra={
                "event": "embedding.exhausted",
                "model": self.model_id,
                "attempts": MAX_ATTEMPTS,
                "error": last_error,
            },
        )
        raise EmbeddingProviderError(
            f"Embedding request failed after {MAX_ATTEMPTS} attempts "
            f"(model={self.model_id}). Last error — {last_error}"
        )

    def _parse(self, body: dict, expected: int) -> list[list[float]]:
        items = body.get("data")
        if not isinstance(items, list) or len(items) != expected:
            raise EmbeddingProviderError(
                f"Provider returned {len(items) if isinstance(items, list) else 'no'} "
                f"embeddings for {expected} inputs."
            )

        # The API does not guarantee ordering; `index` is authoritative.
        ordered = sorted(items, key=lambda d: d.get("index", 0))
        vectors = [item["embedding"] for item in ordered]

        if vectors and not self._dimensions:
            self._dimensions = len(vectors[0])
        return vectors
