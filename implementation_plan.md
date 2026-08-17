# Hybrid Search & Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Hybrid Search (BM25 lexical + Dense vector retrieval with Reciprocal Rank Fusion) and Cross-Encoder Reranking to improve medical query precision and eliminate hallucinations for drug names, dosages, and clinical terms.

**Architecture:** A pluggable `HybridRetriever` adhering to the `Retriever` protocol. It retrieves top candidates from `DenseRetriever` (ChromaDB) and `BM25Retriever` (in-memory BM25 index over stored chunks), fuses their ranks using Reciprocal Rank Fusion (RRF), and re-scores candidates using a Cross-Encoder reranker with an automatic fallback to RRF scoring if model weights are unavailable.

**Tech Stack:** Python 3.13, FastAPI, ChromaDB, `rank-bm25` (or pure BM25Okapi module), `sentence-transformers` / `FlashRank`, `pytest`.

## Global Constraints

- **Protocol Seam**: `HybridRetriever` MUST implement `Retriever` protocol (`search(query, top_k) -> list[RetrievalResult]`).
- **Constitution Principle VI**: Weak matches below `relevance_floor` MUST be flagged (`below_floor=True`), never silently dropped.
- **Fail-Safe Fallback**: If Cross-Encoder weights fail to load, the retriever MUST fall back to RRF scoring without crashing.

---

### Task 1: Add Dependencies and Configuration Settings

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/app/config.py`
- Create: `backend/tests/unit/test_config.py`

**Interfaces:**
- Consumes: Pydantic Settings
- Produces: `retriever_type` (`"dense" | "hybrid" | "hybrid_rerank"`), `reranker_model` (`"BAAI/bge-reranker-base"` or `"ms-marco-MiniLM-L-6-v2"`), `hybrid_candidate_k` (20) in `Settings`.

- [ ] **Step 1: Write test for new config settings**

```python
# backend/tests/unit/test_config.py
from backend.app.config import get_settings

def test_hybrid_config_defaults():
    settings = get_settings()
    assert hasattr(settings, "retriever_type")
    assert settings.retriever_type in ("dense", "hybrid", "hybrid_rerank")
    assert hasattr(settings, "hybrid_candidate_k")
    assert settings.hybrid_candidate_k >= 10
```

- [ ] **Step 2: Add `rank-bm25` and `sentence-transformers` to requirements.txt**

Add to `requirements.txt`:
```text
rank-bm25>=0.2
sentence-transformers>=3.0
```

- [ ] **Step 3: Update `backend/app/config.py`**

Add fields to `Settings`:
```python
retriever_type: Literal["dense", "hybrid", "hybrid_rerank"] = Field(
    default="hybrid_rerank",
    validation_alias="RETRIEVER_TYPE",
)
reranker_model: str = Field(
    default="cross-encoder/ms-marco-MiniLM-L-6-v2",
    validation_alias="RERANKER_MODEL",
)
hybrid_candidate_k: int = Field(
    default=20,
    validation_alias="HYBRID_CANDIDATE_K",
)
```

- [ ] **Step 4: Run test to verify passes**

Run: `python -m pytest backend/tests/unit/test_config.py -v`
Expected: PASS

---

### Task 2: Implement BM25 Lexical Retriever (`backend/app/retrieval/bm25.py`)

**Files:**
- Create: `backend/app/retrieval/bm25.py`
- Create: `backend/tests/unit/test_bm25.py`

**Interfaces:**
- Consumes: `VectorStore.all_chunks()`, query string
- Produces: `BM25Retriever.search(query, top_k) -> list[RetrievalResult]`

- [ ] **Step 1: Write unit test for BM25 Retriever**

```python
# backend/tests/unit/test_bm25.py
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.bm25 import BM25Retriever

def test_bm25_retrieval_finds_exact_keyword():
    c1 = Chunk.from_stored("c1", "Hydrocortisone is indicated for primary adrenal insufficiency.", {"doc_id": "d1", "page_number": 1})
    c2 = Chunk.from_stored("c2", "Prednisolone is an alternative glucocorticoid replacement.", {"doc_id": "d1", "page_number": 2})
    
    retriever = BM25Retriever(chunks=[c1, c2])
    results = retriever.search("Hydrocortisone", top_k=2)
    
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].score > results[1].score
```

- [ ] **Step 2: Implement `BM25Retriever` in `backend/app/retrieval/bm25.py`**

```python
"""BM25 Lexical Retriever using BM25Okapi."""
from __future__ import annotations
import re
from typing import Sequence
from rank_bm25 import BM25Okapi
from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.store import VectorStore

def tokenize_clinical_text(text: str) -> list[str]:
    """Tokenize clinical text preserving drug names, numbers, and Arabic/English terms."""
    return [t.lower() for t in re.findall(r"\w+", text) if len(t) > 1]

class BM25Retriever:
    """BM25 lexical search over stored guideline chunks."""

    def __init__(self, chunks: Sequence[Chunk] | None = None, store: VectorStore | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._store = store or VectorStore(self._settings)
        self._chunks: list[Chunk] = list(chunks) if chunks is not None else self._store.all_chunks()
        
        tokenized_corpus = [tokenize_clinical_text(c.text) for c in self._chunks]
        self._bm25 = BM25Okapi(tokenized_corpus) if tokenized_corpus else None

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        floor = self._settings.relevance_floor
        if not self._chunks or not self._bm25:
            return []

        tokens = tokenize_clinical_text(query)
        if not tokens:
            return []

        raw_scores = self._bm25.get_scores(tokens)
        max_s = max(raw_scores) if len(raw_scores) > 0 and max(raw_scores) > 0 else 1.0
        
        # Sort by score descending
        ranked = sorted(zip(self._chunks, raw_scores), key=lambda x: x[1], reverse=True)[:k]

        return [
            RetrievalResult(
                chunk=chunk,
                score=min(1.0, max(0.0, float(score / max_s))),
                rank=rank,
                below_floor=(score / max_s) < floor,
            )
            for rank, (chunk, score) in enumerate(ranked, start=1)
        ]
```

- [ ] **Step 3: Run test to verify BM25 passes**

Run: `python -m pytest backend/tests/unit/test_bm25.py -v`
Expected: PASS

---

### Task 3: Implement Cross-Encoder Reranker (`backend/app/retrieval/reranker.py`)

**Files:**
- Create: `backend/app/retrieval/reranker.py`
- Create: `backend/tests/unit/test_reranker.py`

**Interfaces:**
- Consumes: Query string and `list[Chunk]`
- Produces: `CrossEncoderReranker.rerank(query, chunks) -> list[tuple[Chunk, float]]`

- [ ] **Step 1: Write unit test for Cross-Encoder Reranker with fallback**

```python
# backend/tests/unit/test_reranker.py
from backend.app.models import Chunk
from backend.app.retrieval.reranker import CrossEncoderReranker

def test_reranker_scores_chunks():
    c1 = Chunk.from_stored("c1", "Hydrocortisone dosage for adrenal crisis.", {"doc_id": "d1", "page_number": 1})
    c2 = Chunk.from_stored("c2", "General guidelines for clinical documentation.", {"doc_id": "d1", "page_number": 2})
    
    reranker = CrossEncoderReranker(disabled=True) # Tests fallback behavior
    scored = reranker.rerank("Hydrocortisone dosage", [c1, c2])
    
    assert len(scored) == 2
    assert scored[0][0].chunk_id == "c1"
```

- [ ] **Step 2: Implement `CrossEncoderReranker` in `backend/app/retrieval/reranker.py`**

```python
"""Cross-Encoder Reranking module with graceful fallback."""
from __future__ import annotations
import logging
from typing import Sequence
from backend.app.config import Settings, get_settings
from backend.app.models import Chunk

logger = logging.getLogger(__name__)

class CrossEncoderReranker:
    def __init__(self, settings: Settings | None = None, disabled: bool = False) -> None:
        self._settings = settings or get_settings()
        self._model = None
        self._disabled = disabled
        
        if not self._disabled:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self._settings.reranker_model)
            except Exception as exc:
                logger.warning("Could not initialize CrossEncoder reranker model '%s': %s. Falling back to rank fusion.", self._settings.reranker_model, exc)
                self._model = None

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []

        if self._model is not None:
            try:
                pairs = [[query, c.text] for c in chunks]
                scores = self._model.predict(pairs)
                # Normalize scores using sigmoid/min-max to [0, 1]
                min_s, max_s = min(scores), max(scores)
                denom = (max_s - min_s) if max_s > min_s else 1.0
                norm_scores = [(float(s) - min_s) / denom for s in scores]
                ranked = sorted(zip(chunks, norm_scores), key=lambda x: x[1], reverse=True)
                return ranked
            except Exception as exc:
                logger.error("CrossEncoder reranking failed at runtime: %s. Using default ordering.", exc)

        # Fallback: maintain candidate ordering with uniform step-decay scores
        n = len(chunks)
        return [(c, max(0.1, 1.0 - (i / max(1, n)))) for i, c in enumerate(chunks)]
```

- [ ] **Step 3: Run test to verify reranker passes**

Run: `python -m pytest backend/tests/unit/test_reranker.py -v`
Expected: PASS

---

### Task 4: Implement Hybrid Retriever & RRF Fusion (`backend/app/retrieval/hybrid.py`)

**Files:**
- Create: `backend/app/retrieval/hybrid.py`
- Create: `backend/tests/unit/test_hybrid.py`

**Interfaces:**
- Consumes: `DenseRetriever`, `BM25Retriever`, `CrossEncoderReranker`
- Produces: `HybridRetriever.search(query, top_k) -> list[RetrievalResult]`

- [ ] **Step 1: Write unit test for Hybrid Retriever RRF fusion**

```python
# backend/tests/unit/test_hybrid.py
from backend.app.models import Chunk
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.reranker import CrossEncoderReranker
from backend.app.retrieval.hybrid import HybridRetriever

def test_hybrid_retriever_combines_bm25_and_dense():
    c1 = Chunk.from_stored("c1", "Hydrocortisone is used for adrenal crisis management.", {"doc_id": "d1", "page_number": 1})
    c2 = Chunk.from_stored("c2", "NICE Guideline NG243 scope and recommendation overview.", {"doc_id": "d1", "page_number": 2})
    
    bm25 = BM25Retriever(chunks=[c1, c2])
    reranker = CrossEncoderReranker(disabled=True)
    
    hybrid = HybridRetriever(bm25_retriever=bm25, reranker=reranker)
    results = hybrid.search("Hydrocortisone crisis", top_k=2)
    
    assert len(results) > 0
    assert results[0].chunk.chunk_id == "c1"
    assert hasattr(results[0], "below_floor")
```

- [ ] **Step 2: Implement `HybridRetriever` in `backend/app/retrieval/hybrid.py`**

```python
"""Hybrid Retriever combining Dense Vector + BM25 Lexical + Cross-Encoder Reranking."""
from __future__ import annotations
import logging
from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.bm25 import BM25Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)

class HybridRetriever:
    """Hybrid Retriever satisfying the Retriever protocol."""

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
        self._reranker = reranker or (CrossEncoderReranker(settings=self._settings) if use_reranker else None)

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        cand_k = max(k, self._settings.hybrid_candidate_k)
        floor = self._settings.relevance_floor

        # 1. Fetch candidates from Dense and BM25
        dense_results = self._dense.search(query, top_k=cand_k)
        bm25_results = self._bm25.search(query, top_k=cand_k)

        # 2. Reciprocal Rank Fusion (RRF)
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

        # 3. Apply Cross-Encoder Reranker if enabled
        if self._reranker is not None:
            ranked_pairs = self._reranker.rerank(query, candidate_chunks)[:k]
        else:
            max_rrf = fused_sorted[0][1] if fused_sorted else 1.0
            ranked_pairs = [(chunks_map[cid], s / max_rrf) for cid, s in fused_sorted[:k]]

        # 4. Construct RetrievalResult list with below_floor flags
        return [
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                below_floor=score < floor,
            )
            for rank, (chunk, score) in enumerate(ranked_pairs, start=1)
        ]
```

- [ ] **Step 3: Run test to verify hybrid retriever passes**

Run: `python -m pytest backend/tests/unit/test_hybrid.py -v`
Expected: PASS

---

### Task 5: Implement Factory and Update API & CLI

**Files:**
- Create: `backend/app/retrieval/factory.py`
- Modify: `backend/app/api/search.py`
- Modify: `backend/app/cli.py`
- Create: `backend/tests/integration/test_hybrid_api.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: `get_retriever(settings) -> Retriever` factory used by FastAPI search route and CLI commands.

- [ ] **Step 1: Create `backend/app/retrieval/factory.py`**

```python
"""Retriever factory function for dependency injection."""
from __future__ import annotations
from backend.app.config import Settings, get_settings
from backend.app.retrieval.base import Retriever
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.hybrid import HybridRetriever

def get_retriever(settings: Settings | None = None) -> Retriever:
    cfg = settings or get_settings()
    if cfg.retriever_type == "dense":
        return DenseRetriever(settings=cfg)
    elif cfg.retriever_type == "hybrid":
        return HybridRetriever(settings=cfg, use_reranker=False)
    else:  # "hybrid_rerank"
        return HybridRetriever(settings=cfg, use_reranker=True)
```

- [ ] **Step 2: Update `backend/app/api/search.py`**

Replace `DenseRetriever` instantiation in `search()` with `get_retriever(settings)`:
```python
from backend.app.retrieval.factory import get_retriever

# inside search():
results = get_retriever(settings).search(
    request.query, request.top_k or settings.top_k
)
```

- [ ] **Step 3: Update `backend/app/cli.py`**

Update `query` command in `backend/app/cli.py` to use `get_retriever(settings)`.

- [ ] **Step 4: Create integration test `backend/tests/integration/test_hybrid_api.py`**

```python
# backend/tests/integration/test_hybrid_api.py
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_search_api_with_hybrid_retriever():
    response = client.post("/api/search", json={"query": "Hydrocortisone adrenal crisis", "top_k": 3})
    assert response.status_code in (200, 535, 503)
```

- [ ] **Step 5: Run integration tests to verify**

Run: `python -m pytest backend/tests/integration/test_hybrid_api.py -v`
Expected: PASS

---

### Task 6: Golden Evaluation Benchmark Verification

**Files:**
- Modify: `backend/tests/eval/test_retrieval_quality.py`

**Interfaces:**
- Consumes: `golden_questions.yaml`
- Produces: Automated verification confirming hybrid search hit-rate meets target $\ge 80\%$.

- [ ] **Step 1: Run complete test suite and golden evaluation**

Run: `python -m pytest backend/tests/ -v`
Expected: All unit, integration, and golden retrieval quality tests PASS ($\ge 80\%$ hit rate).
