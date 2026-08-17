"""Hybrid Retriever combining Dense + BM25 + optional Cross-Encoder (Day 2).

Implements the Retriever protocol (base.py).  Retrieves top candidates from
both DenseRetriever (ChromaDB cosine) and BM25Retriever (in-memory lexical),
fuses their ranks using Reciprocal Rank Fusion (RRF, k=60), and optionally
re-scores using a CrossEncoderReranker.

Constitution Principle VI is enforced: weak matches are flagged with
``below_floor=True``, never silently dropped.
"""

from __future__ import annotations

import logging

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Hybrid Retriever satisfying the Retriever protocol.

    Parameters
    ----------
    dense_retriever : DenseRetriever | None
        Dense cosine retriever.  Created automatically when omitted.
    bm25_retriever : BM25Retriever | None
        BM25 lexical retriever.  Created automatically when omitted.
    reranker : CrossEncoderReranker | None
        Cross-encoder reranker.  Created automatically when *use_reranker*
        is True.
    settings : Settings | None
        Application settings.
    use_reranker : bool
        Whether to apply cross-encoder reranking after RRF fusion.
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        reranker: CrossEncoderReranker | None = None,
        settings: Settings | None = None,
        use_reranker: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._dense = dense_retriever or DenseRetriever(settings=self._settings)
        self._bm25 = bm25_retriever or BM25Retriever(settings=self._settings)
        self._use_reranker = use_reranker
        self._reranker = reranker or (
            CrossEncoderReranker(settings=self._settings)
            if use_reranker
            else None
        )

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        cand_k = max(k, self._settings.hybrid_candidate_k)
        floor = self._settings.relevance_floor

        # --- Stage 1: Dual candidate retrieval ---
        dense_results = self._dense.search(query, top_k=cand_k)
        bm25_results = self._bm25.search(query, top_k=cand_k)

        # --- Stage 2: Reciprocal Rank Fusion (RRF, k=60) ---
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

        fused_sorted = sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        )[:cand_k]
        candidate_chunks = [chunks_map[cid] for cid, _ in fused_sorted]

        if not candidate_chunks:
            return []

        # --- Stage 3: Cross-Encoder Reranking (optional) ---
        if self._reranker is not None:
            ranked_pairs = self._reranker.rerank(query, candidate_chunks)[:k]
        else:
            # Use normalised RRF scores when reranker is disabled.
            max_rrf = fused_sorted[0][1] if fused_sorted else 1.0
            ranked_pairs = [
                (chunks_map[cid], s / max_rrf) for cid, s in fused_sorted[:k]
            ]

        # --- Stage 4: Construct results with below_floor flags ---
        return [
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                below_floor=score < floor,
            )
            for rank, (chunk, score) in enumerate(ranked_pairs, start=1)
        ]
