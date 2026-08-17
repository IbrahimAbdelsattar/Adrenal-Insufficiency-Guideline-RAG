"""Unit tests for Hybrid Retrieval, RRF, and Reranking (Day 2 Lab)."""

from __future__ import annotations

import pytest

from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from backend.app.retrieval.reranker import CrossEncoderReranker


def _make_chunk(cid: str, section: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        text=text,
        document_name="NICE NG243",
        doc_id="nice_ng243",
        source_url="https://nice.org.uk/ng243",
        document_type="guideline",
        publication_year=2024,
        requires_caution=False,
        page_number=1,
        section_number=section,
        section_title=f"Section {section}",
        token_count=30,
    )


def test_reciprocal_rank_fusion():
    c1 = _make_chunk("c1", "1.7", "Hydrocortisone 100mg IV")
    c2 = _make_chunk("c2", "1.3", "Oral hydrocortisone 20mg")
    c3 = _make_chunk("c3", "1.4", "Sick-day dosing rules")

    dense_results = [
        RetrievalResult(chunk=c1, score=0.9, rank=1, below_floor=False),
        RetrievalResult(chunk=c2, score=0.7, rank=2, below_floor=False),
    ]
    bm25_results = [
        RetrievalResult(chunk=c1, score=0.95, rank=1, below_floor=False),
        RetrievalResult(chunk=c3, score=0.80, rank=2, below_floor=False),
    ]

    fused = reciprocal_rank_fusion([dense_results, bm25_results], k_rrf=60)
    assert len(fused) == 3
    # c1 was #1 in both lists, so it must be top ranked in fused
    assert fused[0][0].chunk_id == "c1"
    assert fused[0][1] >= fused[1][1]


def test_reranker_fallback_on_missing_model():
    c1 = _make_chunk("c1", "1.7", "Hydrocortisone 100mg IV")
    results = [RetrievalResult(chunk=c1, score=0.85, rank=1, below_floor=False)]

    reranker = CrossEncoderReranker()
    reranker._load_attempted = True
    reranker._model = None  # simulate offline or uninitialized model

    reranked = reranker.rerank("crisis management", results, top_k=1)
    assert len(reranked) == 1
    assert reranked[0].chunk.chunk_id == "c1"
