"""Hybrid Retriever (Dense + BM25 with Reciprocal Rank Fusion & Reranking).

Combines semantic dense embeddings with lexical BM25 matching to achieve superior
precision across exact terminology and conceptual clinical queries.
"""

from __future__ import annotations

from typing import Sequence

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker
from backend.app.retrieval.store import VectorStore


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

    for ranked_list, weight in zip(ranked_lists, weights):
        for rank, res in enumerate(ranked_list, start=1):
            cid = res.chunk.chunk_id
            chunk_map[cid] = res.chunk
            scores[cid] = scores.get(cid, 0.0) + weight * (1.0 / (k_rrf + rank))

    if not scores:
        return []

    # Min-max scale RRF scores to [0, 1]
    max_score = max(scores.values())
    min_score = min(scores.values())
    spread = max_score - min_score if max_score > min_score else 1.0

    normalized = {
        cid: (s - min_score) / spread if max_score > min_score else s
        for cid, s in scores.items()
    }

    # Sort descending
    sorted_items = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
    return [(chunk_map[cid], score) for cid, score in sorted_items]


class HybridRetriever:
    """Hybrid Dense + BM25 retriever with optional Cross-Encoder reranking."""

    def __init__(
        self,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        reranker: CrossEncoderReranker | None = None,
        store: VectorStore | None = None,
        settings: Settings | None = None,
        candidate_k: int = 20,
        enable_reranker: bool = False,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or VectorStore(self._settings)
        self.dense = dense_retriever or DenseRetriever(store=self._store, settings=self._settings)
        self.bm25 = bm25_retriever or BM25Retriever(store=self._store, settings=self._settings)
        self.reranker = reranker or CrossEncoderReranker(settings=self._settings)
        self.candidate_k = candidate_k
        self.enable_reranker = enable_reranker

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        floor = self._settings.relevance_floor
        cand_k = max(self.candidate_k, k * 2)

        # 1. Retrieve candidates from both systems
        dense_candidates = self.dense.search(query, cand_k)
        bm25_candidates = self.bm25.search(query, cand_k)

        # 2. Fuse via Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion(
            [dense_candidates, bm25_candidates],
            k_rrf=60,
            weights=[1.0, 1.0],
        )

        fused_results = [
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                below_floor=score < floor,
            )
            for rank, (chunk, score) in enumerate(fused, start=1)
        ]

        # 3. Optional Reranking
        if self.enable_reranker:
            return self.reranker.rerank(query, fused_results, top_k=k)

        return fused_results[:k]
