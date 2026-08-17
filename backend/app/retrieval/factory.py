"""Retriever factory for dependency injection (Day 2).

Instantiates the configured retriever strategy:
- "dense": Pure Dense Cosine Retriever (ChromaDB)
- "bm25": Pure BM25 Lexical Retriever
- "hybrid": Dense + BM25 Reciprocal Rank Fusion
- "hybrid_rerank": Hybrid Search + Cross-Encoder Reranking
"""

from __future__ import annotations

import logging
from typing import Literal

from backend.app.config import Settings, get_settings
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)

RetrieverType = Literal["dense", "bm25", "hybrid", "hybrid_rerank"]


def get_retriever(
    retriever_type: str | Settings | None = None,
    store: VectorStore | None = None,
    settings: Settings | None = None,
) -> Retriever:
    """Instantiate a Retriever instance by strategy name or settings."""
    if isinstance(retriever_type, Settings):
        settings = retriever_type
        retriever_type = None

    cfg = settings or get_settings()
    vstore = store or VectorStore(cfg)
    rtype = (retriever_type or cfg.retriever_type).lower()

    logger.debug("Creating retriever: type=%s", rtype)

    if rtype == "dense":
        return DenseRetriever(store=vstore, settings=cfg)
    elif rtype == "bm25":
        return BM25Retriever(store=vstore, settings=cfg)
    elif rtype == "hybrid":
        return HybridRetriever(
            store=vstore,
            settings=cfg,
            use_reranker=False,
        )
    elif rtype in ("hybrid_rerank", "rerank"):
        return HybridRetriever(
            store=vstore,
            settings=cfg,
            use_reranker=True,
        )
    else:
        raise ValueError(
            f"Unknown retriever type '{rtype}'. Supported: 'dense', 'bm25', 'hybrid', 'hybrid_rerank'."
        )
