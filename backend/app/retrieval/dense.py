"""Dense cosine top-K retrieval (FR-021, FR-022, FR-023).

Day 1 baseline. Weak matches are flagged, never filtered — Constitution Principle VI
requires failure modes to stay observable.
"""

from __future__ import annotations

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.models import RetrievalResult
from backend.app.retrieval.store import VectorStore


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
        k = top_k or self._settings.top_k
        floor = self._settings.relevance_floor

        embedding = self.embedder.embed_query(query)
        hits = self._store.query(embedding, k)

        return [
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                below_floor=score < floor,
                dense_score=score,
                retriever_mode="dense"
            )
            for rank, (chunk, score) in enumerate(hits, start=1)
        ]
