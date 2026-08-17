"""Retriever factory for dependency injection (Day 2).

The ``get_retriever()`` function dispatches to the correct implementation
based on ``settings.retriever_type``, keeping the API and CLI layers
decoupled from the concrete retriever choice.
"""

from __future__ import annotations

import logging

from backend.app.config import Settings, get_settings
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)


def get_retriever(settings: Settings | None = None) -> Retriever:
    """Create the retriever configured by ``RETRIEVER_TYPE``.

    Returns
    -------
    Retriever
        One of ``DenseRetriever``, ``HybridRetriever`` (RRF only),
        or ``HybridRetriever`` with cross-encoder reranking.
    """
    cfg = settings or get_settings()
    logger.info("Creating retriever: type=%s", cfg.retriever_type)

    if cfg.retriever_type == "dense":
        return DenseRetriever(settings=cfg)
    elif cfg.retriever_type == "hybrid":
        return HybridRetriever(settings=cfg, use_reranker=False)
    else:  # "hybrid_rerank"
        return HybridRetriever(settings=cfg, use_reranker=True)
