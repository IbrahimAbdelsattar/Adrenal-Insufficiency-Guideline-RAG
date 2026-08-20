"""Dense cosine top-K retrieval (FR-021, FR-022, FR-023).

Day 1 baseline. Weak matches are flagged, never filtered — Constitution Principle VI
requires failure modes to stay observable. Supports fallback embedding models
and target collections.
"""

from __future__ import annotations

import logging

from backend.app.config import Settings, get_settings
from backend.app.embeddings.base import Embedder
from backend.app.embeddings.fallback import FallbackEmbedder
from backend.app.models import RetrievalResult
from backend.app.monitoring import stage_timer, trace_span
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Cosine similarity over the ChromaDB collection with fallback resilience."""

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
            if self._settings.enable_embedding_fallback:
                self._embedder = FallbackEmbedder(settings=self._settings)
            else:
                from backend.app.embeddings.openrouter import OpenRouterEmbedder

                self._embedder = OpenRouterEmbedder(self._settings)
        return self._embedder

    def _ensure_fallback_collection(self, fallback_col: str) -> None:
        """Populate fallback collection on the fly if primary collection has chunks but fallback does not."""
        if self._store.is_ready(fallback_col):
            return
        chunks = self._store.all_chunks(self._store.collection_name)
        if not chunks:
            return
        logger.info(
            "Auto-populating fallback vector collection '%s' from %d stored chunks using fallback embedder...",
            fallback_col,
            len(chunks),
            extra={"event": "retrieval.dense.auto_populate_fallback", "chunks": len(chunks)},
        )
        texts = [c.text for c in chunks]
        if isinstance(self.embedder, FallbackEmbedder):
            embeddings = self.embedder.secondary.embed_documents(texts)
        else:
            embeddings = self.embedder.embed_documents(texts)
        self._store.build(chunks, embeddings, collection_name=fallback_col)
        logger.info(
            "Fallback vector collection '%s' is now ready with %d chunks.",
            fallback_col,
            len(chunks),
        )

    def _resolve_target_collection(self) -> str:
        """Determine whether to query the primary or fallback vector collection."""
        if getattr(self.embedder, "is_fallback_active", False):
            fallback_col = self._store.fallback_collection_name
            self._ensure_fallback_collection(fallback_col)
            if self._store.is_ready(fallback_col):
                return fallback_col
        return self._store.collection_name

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        with trace_span(op="rag.dense.search", description="Dense Vector Search"):
            k = top_k or self._settings.top_k
            floor = self._settings.relevance_floor

            # Embedding and the vector scan are timed apart: a slow dense stage
            # is almost always the remote embedding call, not Chroma.
            with stage_timer("retrieval.dense.embed", logger, top_k=k) as span:
                embedding = self.embedder.embed_query(query)
                span["dims"] = len(embedding)

            target_collection = self._resolve_target_collection()

            with stage_timer(
                "retrieval.dense.query", logger, top_k=k, collection=target_collection
            ) as span:
                try:
                    hits = self._store.query(embedding, k, collection_name=target_collection)
                except Exception as exc:
                    # If query failed (e.g. dimension mismatch), auto-populate fallback collection and retry
                    fallback_col = self._store.fallback_collection_name
                    self._ensure_fallback_collection(fallback_col)
                    if self._store.is_ready(fallback_col):
                        logger.warning(
                            "Dense query against '%s' failed (%s). Retrying against fallback collection '%s'.",
                            target_collection,
                            exc,
                            fallback_col,
                        )
                        hits = self._store.query(embedding, k, collection_name=fallback_col)
                        target_collection = fallback_col
                    else:
                        raise

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
                "retrieval.dense results=%d above_floor=%d top_score=%.4f (collection=%s)",
                len(results),
                sum(1 for r in results if not r.below_floor),
                results[0].score if results else 0.0,
                target_collection,
                extra={
                    "event": "retrieval.dense",
                    "results": len(results),
                    "above_floor": sum(1 for r in results if not r.below_floor),
                    "relevance_floor": floor,
                    "collection": target_collection,
                    "chunk_ids": [r.chunk.chunk_id for r in results],
                },
            )
            return results
