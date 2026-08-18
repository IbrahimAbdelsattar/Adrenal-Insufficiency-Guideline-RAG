"""Retriever factory for dependency injection (Day 2).

Instantiates the configured retriever strategy:
- "dense": Pure Dense Cosine Retriever (ChromaDB)
- "bm25": Pure BM25 Lexical Retriever
- "hybrid": Dense + BM25 Reciprocal Rank Fusion
- "hybrid_rerank": Hybrid Search + Cross-Encoder Reranking
"""

from __future__ import annotations

import logging
import threading
from typing import Literal

from backend.app.config import Settings, get_settings
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)

RetrieverType = Literal["dense", "bm25", "hybrid", "hybrid_rerank"]

_STORE_LOCK = threading.Lock()
_shared_store: VectorStore | None = None

_RETRIEVER_LOCK = threading.Lock()
_shared_retriever: Retriever | None = None


def get_shared_store(settings: Settings | None = None) -> VectorStore:
    """Process-wide VectorStore.

    Each VectorStore opens the persistent ChromaDB client; rebuilding it per
    request reopens the on-disk index every time.
    """
    global _shared_store
    if _shared_store is None:
        with _STORE_LOCK:
            if _shared_store is None:
                _shared_store = VectorStore(settings or get_settings())
    return _shared_store


def get_shared_retriever(settings: Settings | None = None) -> Retriever:
    """Process-wide cached retriever for request handling.

    Building a retriever reads every chunk from Chroma and tokenizes the whole
    corpus for BM25, and a fresh embedder loses its query cache — doing that
    per request wastes hundreds of milliseconds. Call reset_shared_retriever()
    after re-ingesting in the same process.
    """
    global _shared_retriever
    if _shared_retriever is None:
        with _RETRIEVER_LOCK:
            if _shared_retriever is None:
                _shared_retriever = get_retriever(
                    settings=settings, store=get_shared_store(settings)
                )
    return _shared_retriever


def reset_shared_retriever() -> None:
    """Drop the cached retriever (e.g. after an index rebuild)."""
    global _shared_retriever
    with _RETRIEVER_LOCK:
        _shared_retriever = None


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
