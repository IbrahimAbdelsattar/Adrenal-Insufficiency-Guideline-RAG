"""Hybrid Retriever combining Dense + BM25 + optional Cross-Encoder (Day 2).

Implements the Retriever protocol (base.py). Retrieves top candidates from
both DenseRetriever (ChromaDB cosine) and BM25Retriever (in-memory lexical),
fuses their ranks using Reciprocal Rank Fusion (RRF, k=60), and optionally
re-scores using a CrossEncoderReranker.

Constitution Principle VI is enforced: weak matches are flagged with
below_floor=True, never silently dropped.
"""

from __future__ import annotations

import logging

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]],
    k_rrf: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[Chunk, float]]:
    """Combine multiple ranked lists using standard Reciprocal Rank Fusion."""
    if not ranked_lists:
        return []

    weights = weights or [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    chunk_map: dict[str, Chunk] = {}

    for ranked_list, weight in zip(ranked_lists, weights, strict=False):
        for rank, res in enumerate(ranked_list, start=1):
            cid = res.chunk.chunk_id
            chunk_map[cid] = res.chunk
            scores[cid] = scores.get(cid, 0.0) + weight * (1.0 / (k_rrf + rank))

    if not scores:
        return []

    max_score = max(scores.values())
    min_score = min(scores.values())
    spread = max_score - min_score if max_score > min_score else 1.0

    normalized = {
        cid: (s - min_score) / spread if max_score > min_score else s for cid, s in scores.items()
    }

    sorted_items = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
    return [(chunk_map[cid], score) for cid, score in sorted_items]


class HybridRetriever:
    """Hybrid Retriever satisfying the Retriever protocol."""

    def __init__(
        self,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        reranker: CrossEncoderReranker | None = None,
        store: VectorStore | None = None,
        settings: Settings | None = None,
        candidate_k: int | None = None,
        use_reranker: bool = False,
        enable_reranker: bool | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or VectorStore(self._settings)
        self._dense = dense_retriever or DenseRetriever(store=self._store, settings=self._settings)
        self._bm25 = bm25_retriever or BM25Retriever(store=self._store, settings=self._settings)

        # Support both use_reranker and enable_reranker naming
        should_rerank = enable_reranker if enable_reranker is not None else use_reranker
        self._use_reranker = should_rerank
        self._candidate_k = candidate_k or self._settings.hybrid_candidate_k
        self._reranker = reranker or (
            CrossEncoderReranker(settings=self._settings) if should_rerank else None
        )

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        cand_k = max(k, self._candidate_k)
        floor = self._settings.relevance_floor

        # Stage 1: Dual candidate retrieval
        dense_results = self._dense.search(query, top_k=cand_k)
        bm25_results = self._bm25.search(query, top_k=cand_k)

        # Stage 2: Reciprocal Rank Fusion (RRF, k=60)
        rrf_k = 60.0
        scores: dict[str, float] = {}
        chunks_map: dict[str, Chunk] = {}

        for rank, res in enumerate(dense_results, start=1):
            cid = res.chunk.chunk_id
            chunks_map[cid] = res.chunk
            scores[cid] = scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        for rank, res in enumerate(bm25_results, start=1):
            cid = res.chunk.chunk_id
            chunks_map[cid] = res.chunk
            scores[cid] = scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))

        fused_sorted = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:cand_k]
        candidate_chunks = [chunks_map[cid] for cid, _ in fused_sorted]

        if not candidate_chunks:
            return []

        # Stage 3: Cross-Encoder Reranking (optional)
        if self._reranker is not None:
            ranked_pairs = self._reranker.rerank(query, candidate_chunks)[:k]
        else:
            max_rrf = fused_sorted[0][1] if fused_sorted else 1.0
            ranked_pairs = [(chunks_map[cid], s / max_rrf) for cid, s in fused_sorted[:k]]

        dense_map = {res.chunk.chunk_id: res.score for res in dense_results}
        bm25_map = {res.chunk.chunk_id: res.score for res in bm25_results}

        # Stage 4: Construct results with below_floor and diagnostic scores
        results = []
        for rank, (chunk, score) in enumerate(ranked_pairs, start=1):
            cid = chunk.chunk_id
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    rank=rank,
                    below_floor=score < floor,
                    dense_score=dense_map.get(cid, 0.0),
                    bm25_score=bm25_map.get(cid, 0.0),
                    rerank_score=score if self._reranker is not None else None,
                    retriever_mode="hybrid_rerank" if self._reranker is not None else "hybrid",
                )
            )
        return results
