"""High-performance TTL + LRU cache with automatic index manifest invalidation."""

from __future__ import annotations

import logging
import re
import string
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


def normalize_query(query: str) -> str:
    """Normalize a clinical query string for semantic cache lookup.

    Performs Unicode NFKC normalization, lowercasing, whitespace collapsing,
    and stripping of edge punctuation while preserving medical abbreviations and hyphenation.
    """
    if not query:
        return ""
    # Normalize unicode characters
    normalized = unicodedata.normalize("NFKC", query).strip().lower()
    # Collapse multiple whitespace characters
    normalized = re.sub(r"\s+", " ", normalized)
    # Strip leading/trailing punctuation but keep internal hyphens and decimals (e.g. 1.7.1)
    normalized = normalized.strip(string.punctuation + " \t\r\n")
    return normalized


class TTLLRUCache(Generic[K, V]):
    """Thread-safe, memory-bounded Least-Recently-Used (LRU) cache with Time-To-Live (TTL)

    and automatic invalidation on index manifest modification.
    """

    def __init__(
        self,
        maxsize: int = 512,
        ttl_seconds: float = 3600.0,
        manifest_path: Path | None = None,
        name: str = "cache",
    ) -> None:
        self.maxsize = max(1, maxsize)
        self.ttl_seconds = max(0.0, ttl_seconds)
        self.manifest_path = manifest_path
        self.name = name
        self._cache: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._last_manifest_mtime: float | None = self._read_manifest_mtime()
        self._hits: int = 0
        self._misses: int = 0

    def _read_manifest_mtime(self) -> float | None:
        if self.manifest_path and self.manifest_path.exists():
            try:
                return self.manifest_path.stat().st_mtime
            except OSError:
                return None
        return None

    def check_manifest_invalidation(self) -> bool:
        """Check if the underlying index manifest changed on disk and invalidate if stale."""
        current_mtime = self._read_manifest_mtime()
        if current_mtime != self._last_manifest_mtime:
            logger.info(
                "Index manifest modification detected on '%s' (mtime changed: %s -> %s). Flushing cache.",
                self.name,
                self._last_manifest_mtime,
                current_mtime,
            )
            self._cache.clear()
            self._last_manifest_mtime = current_mtime
            return True
        return False

    def get(self, key: K) -> V | None:
        """Retrieve an unexpired value by key, moving it to the most recently used position."""
        self.check_manifest_invalidation()

        if key not in self._cache:
            self._misses += 1
            return None

        expires_at, value = self._cache[key]
        now = time.monotonic()

        if self.ttl_seconds > 0 and now > expires_at:
            # Expired entry
            del self._cache[key]
            self._misses += 1
            return None

        # Cache Hit: Refresh LRU order
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def put(self, key: K, value: V) -> None:
        """Insert or update a cache entry, evicting the oldest entry if max capacity is exceeded."""
        self.check_manifest_invalidation()

        now = time.monotonic()
        expires_at = now + self.ttl_seconds if self.ttl_seconds > 0 else float("inf")

        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (expires_at, value)

        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Flush all cache entries and reset metrics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._last_manifest_mtime = self._read_manifest_mtime()

    def __len__(self) -> int:
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Return cache performance statistics."""
        total = self._hits + self._misses
        hit_ratio = round((self._hits / total) if total > 0 else 0.0, 4)
        return {
            "name": self.name,
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_ratio": hit_ratio,
        }
