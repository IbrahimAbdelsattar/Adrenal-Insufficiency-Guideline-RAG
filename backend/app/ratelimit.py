"""Simple token-bucket rate limiter for provider token usage.

This module provides a process-global TokenBucketRateLimiter and a small
token estimation helper. It is intentionally conservative: token estimates
are based on character counts (chars / 4) and rounded up.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Iterable

from backend.app.config import get_settings
from backend.app.errors import PipelineError


class RateLimitExceeded(PipelineError):
    """Raised when the configured token budget would be exceeded."""


class TokenBucketRateLimiter:
    def __init__(self, capacity_per_minute: int) -> None:
        self.capacity = float(max(0, capacity_per_minute))
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        # refill rate = capacity per 60 seconds
        refill = (elapsed / 60.0) * self.capacity
        if refill > 0:
            self._tokens = min(self.capacity, self._tokens + refill)
            self._last = now

    def try_consume(self, tokens: int) -> bool:
        with self._lock:
            self._refill()
            if tokens <= self._tokens:
                self._tokens -= tokens
                return True
            return False

    def consume_or_raise(self, tokens: int) -> None:
        if tokens <= 0:
            return
        if not self.try_consume(tokens):
            raise RateLimitExceeded(
                f"Rate limit exceeded: need {tokens} tokens but only {int(self._tokens)} available"
            )


_GLOBAL: TokenBucketRateLimiter | None = None


def get_global_rate_limiter() -> TokenBucketRateLimiter:
    global _GLOBAL
    if _GLOBAL is None:
        settings = get_settings()
        _GLOBAL = TokenBucketRateLimiter(settings.token_rate_limit_per_minute)
    return _GLOBAL


def estimate_tokens_for_texts(texts: Iterable[str]) -> int:
    """Very small token estimator: chars / 4 rounded up per text.

    This avoids adding a heavy dependency like `tiktoken` while still giving a
    conservative budget for rate-limiting.
    """
    total = 0
    for t in texts:
        if not t:
            continue
        chars = len(t)
        # approximate tokens
        tokens = math.ceil(chars / 4)
        total += tokens
    return max(0, int(total))
