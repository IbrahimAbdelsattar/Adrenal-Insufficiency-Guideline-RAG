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

    def _embedder_for_fallback(self) -> Embedder:
        """The embedder whose vectors the fallback collection must be built from."""
        embedder = self.embedder
        return embedder.secondary if isinstance(embedder, FallbackEmbedder) else embedder

    def _ensure_fallback_collection(self, fallback_col: str) -> None:
        """Build the fallback collection if it is missing, empty, or the wrong width.

        A collection built by a different embedder is worse than an empty one: it
        looks ready, so it is never rebuilt, and every query against it dies on a
        dimension mismatch. Comparing the stored width to the embedder's own
        catches that and forces a rebuild.
        """
        if self._store.is_ready(fallback_col):
            stored_dims = self._store.dimension_of(fallback_col)
            expected_dims = getattr(self._embedder_for_fallback(), "dimensions", 0)
            if not stored_dims or not expected_dims or stored_dims == expected_dims:
                return
            logger.warning(
                "Fallback collection '%s' holds %d-dimensional vectors but the active "
                "embedder produces %d. Rebuilding it.",
                fallback_col,
                stored_dims,
                expected_dims,
                extra={
                    "event": "retrieval.dense.fallback_dim_mismatch",
                    "collection": fallback_col,
                    "stored_dimensions": stored_dims,
                    "expected_dimensions": expected_dims,
                },
            )
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
        try:
            embeddings = self._embedder_for_fallback().embed_documents(texts)
        except Exception as exc:
            # This runs on the request path, and the embedder it needs is the one
            # that is already in trouble (that is why we are in the fallback path
            # at all). Re-embedding the whole corpus through it is exactly what
            # fails -- so give up on the fallback collection rather than letting
            # the exception take dense retrieval down with it.
            logger.warning(
                "Could not build fallback collection '%s' (%s). "
                "Continuing against the primary collection.",
                fallback_col,
                exc,
                extra={
                    "event": "retrieval.dense.fallback_build_failed",
                    "collection": fallback_col,
                    "chunks": len(chunks),
                    "error": str(exc),
                },
            )
            return
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
                    # If the query failed (e.g. dimension mismatch), rebuild the
                    # fallback collection with the embedder we are actually using
                    # and retry there. Retrying against the collection that just
                    # failed only reproduces the same error, so bail out instead
                    # and let the caller degrade to BM25.
                    fallback_col = self._store.fallback_collection_name
                    if target_collection == fallback_col:
                        raise
                    self._ensure_fallback_collection(fallback_col)
                    if not self._store.is_ready(fallback_col):
                        raise
                    logger.warning(
                        "Dense query against '%s' failed (%s). Retrying against fallback collection '%s'.",
                        target_collection,
                        exc,
                        fallback_col,
                    )
                    hits = self._store.query(embedding, k, collection_name=fallback_col)
                    target_collection = fallback_col

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
