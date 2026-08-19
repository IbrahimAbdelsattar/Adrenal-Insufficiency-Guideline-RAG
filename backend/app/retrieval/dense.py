"""Dense cosine top-K retrieval (FR-021, FR-022, FR-023).

Day 1 baseline. Weak matches are flagged, never filtered — Constitution Principle VI
requires failure modes to stay observable.
"""

from __future__ import annotations

import logging

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.models import RetrievalResult
from backend.app.monitoring import stage_timer, trace_span
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Cosine similarity over the ChromaDB collection."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or VectorStore(self._settings)
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        # Deferred so constructing a retriever never requires an API key.
        if self._embedder is None:
            from backend.app.embeddings.openrouter import OpenRouterEmbedder

            self._embedder = OpenRouterEmbedder(self._settings)
        return self._embedder

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        with trace_span(op="rag.dense.search", description="Dense Vector Search"):
            k = top_k or self._settings.top_k
            floor = self._settings.relevance_floor

            # Embedding and the vector scan are timed apart: a slow dense stage
            # is almost always the remote embedding call, not Chroma.
            with stage_timer("retrieval.dense.embed", logger, top_k=k) as span:
                embedding = self.embedder.embed_query(query)
                span["dims"] = len(embedding)

            with stage_timer("retrieval.dense.query", logger, top_k=k) as span:
                hits = self._store.query(embedding, k)
                span["hits"] = len(hits)
                span["top_score"] = round(hits[0][1], 4) if hits else 0.0

            results = [
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    rank=rank,
                    below_floor=score < floor,
                    dense_score=score,
                    retriever_mode="dense",
                )
                for rank, (chunk, score) in enumerate(hits, start=1)
            ]

            logger.debug(
                "retrieval.dense results=%d above_floor=%d top_score=%.4f",
                len(results),
                sum(1 for r in results if not r.below_floor),
                results[0].score if results else 0.0,
                extra={
                    "event": "retrieval.dense",
                    "results": len(results),
                    "above_floor": sum(1 for r in results if not r.below_floor),
                    "relevance_floor": floor,
                    "chunk_ids": [r.chunk.chunk_id for r in results],
                },
            )
            return results
