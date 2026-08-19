"""Simple demo/test for the TokenBucketRateLimiter.

Run as a module from the repo root:

    python -m backend.app.ratelimit_test

This script creates a small-capacity limiter and demonstrates consumption
and refill behavior without touching provider APIs.
"""

from __future__ import annotations

import time

from backend.app.ratelimit import TokenBucketRateLimiter, estimate_tokens_for_texts


def try_consume(limiter: TokenBucketRateLimiter, n: int) -> None:
    ok = limiter.try_consume(n)
    print(f"consume {n:3d} -> {'OK' if ok else 'FAILED'}; tokens_left={int(limiter._tokens)}")


def main() -> None:
    print("Rate limiter demo: capacity=20 tokens/min")
    limiter = TokenBucketRateLimiter(20)

    sample_texts = [
        "Short prompt for generation.",
        "Another short prompt.",
        "A longer text that will use more tokens when estimated by the simple estimator.",
    ]
    est = estimate_tokens_for_texts(sample_texts)
    print(f"Estimated tokens for sample_texts (3 items): {est}")

    print("\nImmediate consumes:")
    try_consume(limiter, 8)
    try_consume(limiter, 8)
    try_consume(limiter, 6)

    print("\nWaiting 30 seconds to observe refill (half a minute)...")
    time.sleep(30)
    print(f"After 30s wait tokens_available={int(limiter._tokens)}")

    print("\nConsume after refill:")
    try_consume(limiter, 6)

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
