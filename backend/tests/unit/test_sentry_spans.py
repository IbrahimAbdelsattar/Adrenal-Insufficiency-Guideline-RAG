"""Unit tests verifying Sentry span tracing in retrieval and generation pipelines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.config import Settings
from backend.app.generation.client import LLMClient
from backend.app.models import Chunk
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker


def make_test_chunk(chunk_id: str = "c1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text="Clinical guideline content for tests",
        document_name="Test Doc",
        doc_id="d1",
        source_url="https://example.com/doc",
        document_type="guideline",
        publication_year=2024,
        requires_caution=False,
        page_number=1,
        section_title="Title",
        token_count=10,
    )


def test_dense_retriever_traces_span():
    """DenseRetriever wraps search in trace_span context manager."""
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_store = MagicMock()
    mock_store.query.return_value = []

    retriever = DenseRetriever(embedder=mock_embedder, store=mock_store)

    with patch("backend.app.retrieval.dense.trace_span") as mock_trace:
        retriever.search("clinical query")
        mock_trace.assert_called_with(op="rag.dense.search", description="Dense Vector Search")


def test_hybrid_retriever_traces_span():
    """HybridRetriever wraps reciprocal rank fusion and search in trace_span."""
    mock_dense = MagicMock()
    mock_dense.search.return_value = []
    mock_bm25 = MagicMock()
    mock_bm25.search.return_value = []

    retriever = HybridRetriever(dense_retriever=mock_dense, bm25_retriever=mock_bm25)

    with patch("backend.app.retrieval.hybrid.trace_span") as mock_trace:
        retriever.search("clinical query")
        mock_trace.assert_called_with(
            op="rag.hybrid.search", description="Hybrid Dense + BM25 Search"
        )


def test_cross_encoder_reranker_traces_span():
    """CrossEncoderReranker wraps reranking inference in trace_span."""
    reranker = CrossEncoderReranker(disabled=True)
    chunks = [make_test_chunk("c1")]
    with patch("backend.app.retrieval.reranker.trace_span") as mock_trace:
        reranker.rerank("query", chunks)
        mock_trace.assert_called_with(op="rag.reranker.rerank", description="CrossEncoder Rerank")


@pytest.mark.asyncio
async def test_llm_client_traces_span():
    """LLMClient wraps generate_completion in trace_span."""
    settings = Settings(openrouter_api_key="test-key")
    client = LLMClient(settings=settings)

    with patch("backend.app.generation.client.trace_span") as mock_trace:
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "Answer"}}]},
            )
            await client.generate_completion("system", "user")
            mock_trace.assert_called_with(
                op="llm.generate", description="OmniRoute Chat Completion"
            )
