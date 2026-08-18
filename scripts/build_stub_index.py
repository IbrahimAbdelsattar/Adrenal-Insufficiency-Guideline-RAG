"""Build a deterministic, API-key-free index for CI smoke tests.

The production entrypoint (docker-entrypoint.sh) exits when no index exists
and no OMNIROUTE_API_KEY is set, so the CI smoke-test container (which has
neither) could never start. This script ingests the registered corpus with a
hash-based stub embedder, producing a real ChromaDB index + manifest +
graph.json that the entrypoint detects and the API can serve.

Not for production use — the embeddings are meaningless vectors.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# Allow running directly: python scripts/build_stub_index.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import get_settings
from backend.app.ingestion.pipeline import run_ingest

DIMENSIONS = 32


class StubEmbedder:
    """Deterministic pseudo-embeddings derived from the text hash."""

    model_id = "stub/deterministic-ci-embedder"
    dimensions = DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(DIMENSIONS)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def main() -> None:
    settings = get_settings()
    print(f"Building stub index into {settings.index_path} ...")
    result = run_ingest(settings=settings, embedder=StubEmbedder(), report=print)
    print(f"Stub index ready: {result.chunk_count} chunks, {result.oversized_count} oversized")


if __name__ == "__main__":
    main()
