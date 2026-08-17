"""Retriever factory (Day 2 Lab).

Instantiates the configured retriever strategy:
- "dense": Pure Dense Cosine Retriever (ChromaDB)
- "bm25": Pure BM25 Lexical Retriever
- "hybrid": Dense + BM25 Reciprocal Rank Fusion
- "hybrid_rerank": Hybrid Search + Cross-Encoder Reranking
"""

from __future__ import annotations

from typing import Literal

from backend.app.config import Settings, get_settings
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker
from backend.app.retrieval.store import VectorStore

RetrieverType = Literal["dense", "bm25", "hybrid", "hybrid_rerank"]


def get_retriever(
    retriever_type: str | None = None,
    store: VectorStore | None = None,
    settings: Settings | None = None,
) -> Retriever:
    """Instantiate a Retriever instance by strategy name or settings."""
    settings = settings or get_settings()
    store = store or VectorStore(settings)
    rtype = (retriever_type or settings.retriever_type).lower()

    if rtype == "dense":
        return DenseRetriever(store=store, settings=settings)
    elif rtype == "bm25":
        return BM25Retriever(store=store, settings=settings)
    elif rtype == "hybrid":
        return HybridRetriever(
            store=store,
            settings=settings,
            enable_reranker=False,
        )
    elif rtype in ("hybrid_rerank", "rerank"):
        return HybridRetriever(
            store=store,
            settings=settings,
            enable_reranker=True,
        )
    else:
        raise ValueError(
            f"Unknown retriever type '{rtype}'. Supported: 'dense', 'bm25', 'hybrid', 'hybrid_rerank'."
        )
