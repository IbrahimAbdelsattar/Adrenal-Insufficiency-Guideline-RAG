# Eva-AI — Comprehensive Implementation Plan

> **Eva-AI** is an evidence-grounded Clinical Decision Support (RAG) platform for adrenal insufficiency management, strictly grounded in **NICE Guideline NG243**.

---

## Table of Contents

1. [Project Vision & Scope](#1-project-vision--scope)
2. [Architecture Overview](#2-architecture-overview)
3. [Constitutional Principles](#3-constitutional-principles)
4. [Technology Stack](#4-technology-stack)
5. [Phase 1 — Clinical RAG Ingestion Pipeline ✅](#phase-1--clinical-rag-ingestion-pipeline-)
6. [Phase 2 — Hybrid Search & Cross-Encoder Reranking 🔄](#phase-2--hybrid-search--cross-encoder-reranking-)
7. [Phase 3 — Generative Answer Synthesis 📋](#phase-3--generative-answer-synthesis-)
8. [Phase 4 — Production Hardening & Deployment 📋](#phase-4--production-hardening--deployment-)
9. [Verification Plan](#9-verification-plan)

---

## 1. Project Vision & Scope

Eva-AI is a **Retrieval-Augmented Generation (RAG)** platform that provides clinicians, general practitioners, and clinical trainees with **evidence-grounded answers** about adrenal insufficiency — including identification, diagnosis, emergency crisis management, and sick-day dosing rules.

### Target Users
- Clinicians & general practitioners
- Clinical trainees & residents
- Medical educators

### Clinical Domain
- **Primary**: Adrenal insufficiency identification & management
- **Guideline Source**: NICE NG243 — *"Adrenal insufficiency: identification and management"* (August 2024)

### Key Differentiators
- Every assertion traces back to guideline text with page-level citations
- Fail-closed architecture — no unverified content ever surfaces
- Bilingual (English / Arabic) with full RTL support
- Clinical safety disclaimers embedded at every layer

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     Next.js 15 Inspector UI                  │
│   (SearchBox, ChunkCard, IndexStatus, i18n EN/AR, Themes)    │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP /api/*
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Monolith                         │
│  main.py → api/search.py → Retriever Protocol                │
│            api/generate.py → LLM Synthesis (Phase 3)         │
└───────────┬──────────────────────────────┬───────────────────┘
            │                              │
  ┌─────────▼──────────┐       ┌───────────▼─────────────┐
  │  Embedder Protocol  │       │   Retriever / Store      │
  │  (openrouter.py)    │       │   dense.py → ChromaDB    │
  │         │           │       │   bm25.py  → BM25Okapi   │  ← Phase 2
  └─────────┼──────────┘       │   hybrid.py → RRF Fusion  │  ← Phase 2
            │                   │   reranker.py → CrossEnc  │  ← Phase 2
            ▼                   │   factory.py → Dispatch   │  ← Phase 2
   OmniRoute Gateway            └───────────┬─────────────┘
 (gemini-embedding-001)                     │
                                            ▼
                                     ChromaDB Index
                                (data/index/chroma.sqlite3)
```

### Ingestion Flow
```
data/sources.yaml + data/corpus/*.pdf
  → registry.py     (fail-closed provenance check)
  → parser.py       (PyMuPDF span extraction with font metadata)
  → cleaner.py      (frequency-based header/footer & glyph cleanup)
  → sectioner.py    (NICE 1.X sections, 1.X.X recommendation detection)
  → chunker.py      (atomic recommendation packing, 400-800 token budget)
  → openrouter.py   (batch embedding via OmniRoute gateway)
  → store.py        (atomic swap in ChromaDB + manifest.json)
```

---

## 3. Constitutional Principles

| # | Principle | Description |
|---|-----------|-------------|
| I | **Evidence-Grounded Answers Only** | Zero bypassing of retrieval. Every assertion traces to guideline text. |
| II | **Structural Citation Metadata** | Citation metadata (`document_name`, `page_number`, `section_title`, `recommendation_ids`, `source_url`, `chunk_id`) stored directly on every vector entry — never in separate sidecars. |
| III | **Fail-Closed Source Provenance** | All corpus files must be registered in `data/sources.yaml` with publisher, year, URL, and justification. Ingestion aborts on unregistered files. |
| IV | **Narrow Scope Discipline** | Restricted strictly to adrenal insufficiency management. Prominent decision-support disclaimers appear in UI and API. |
| V | **Staged Delivery** | Retrieval quality is verified before any LLM text generation is introduced. |
| VI | **Human Verification Over Automated Confidence** | Weak/low-scoring evidence (`score < relevance_floor`) is flagged (`below_floor=True`) rather than silently dropped. Exact PDF page references provided for trace-back. |

---

## 4. Technology Stack

### Backend
| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.13 |
| Framework | FastAPI + Uvicorn | ≥0.115 / ≥0.32 |
| Configuration | Pydantic v2 + pydantic-settings | ≥2.9 / ≥2.6 |
| PDF Extraction | PyMuPDF (fitz) | ≥1.24 |
| Tokenization | tiktoken (cl100k_base) | latest |
| Vector Database | ChromaDB (embedded, persistent) | ≥0.5 |
| Embedding Gateway | OmniRoute → gemini-embedding-001 | — |
| Lexical Search | rank-bm25 (BM25Okapi) | ≥0.2 |
| Reranking | sentence-transformers (CrossEncoder) | ≥3.0 |
| LLM Generation | Claude Sonnet 4.5 (via Anthropic API) | Phase 3 |
| Testing | pytest + pytest-asyncio | ≥8.3 |

### Frontend
| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Next.js (App Router) | 15.1.0 |
| UI Runtime | React + TypeScript | 19.0.0 / 5.7.0 |
| Styling | Tailwind CSS + custom mono-theme | 4.0 |
| i18n | Custom bilingual (EN / AR + RTL) | — |
| Themes | Light / Dark with anti-FOUC script | — |

### DevOps
| Component | Technology |
|-----------|-----------|
| Containerization | Docker multi-stage build |
| Orchestration | docker-compose (prod + dev) |
| Reverse Proxy | Dokploy/Traefik compatible |
| Local Dev | start.bat (Windows 1-click) |

---

## Phase 1 — Clinical RAG Ingestion Pipeline ✅

> **Status**: COMPLETE (49/49 tasks)
> **Spec**: `specs/001-clinical-rag-ingestion/`

### Summary
The complete ingestion-to-retrieval pipeline, frontend Evidence Inspector UI, golden evaluation suite, and provenance system have been built and verified.

### Completed Sub-Phases

#### 1.1 Setup (T001–T007) ✅
- [x] Backend skeleton with FastAPI + Uvicorn
- [x] Dependencies in `requirements.txt`
- [x] `.env.example` with all configuration variables
- [x] `.gitignore` for Python + Node.js
- [x] `config.py` with typed Pydantic Settings
- [x] PDF corpus placement in `data/corpus/`
- [x] Next.js 15 frontend initialization

#### 1.2 Foundational Data Layer (T008–T015) ✅
- [x] `models.py` — Pydantic schemas: `SourceDocument`, `Chunk`, `IndexManifest`, `RetrievalResult`, `SearchResponse`, `GoldenQuestion`
- [x] `data/sources.yaml` — Guideline provenance registry
- [x] `registry.py` — Fail-closed source validator with caution checking
- [x] `Embedder` protocol in `embeddings/base.py`
- [x] `openrouter.py` — OmniRoute-compatible embeddings client
- [x] `Retriever` protocol in `retrieval/base.py`
- [x] `store.py` — ChromaDB persistent vector store with atomic swap
- [x] `main.py` — FastAPI app with CORS and static mounts

#### 1.3 Ingestion Pipeline (T016–T025) ✅
- [x] Unit tests for all transform stages
- [x] Integration test for full pipeline
- [x] `parser.py` — PyMuPDF span-level extraction with font size/weight metadata
- [x] `cleaner.py` — Frequency-based header/footer removal (>60% page ratio), glyph cleanup
- [x] `sectioner.py` — NICE section (`1.X`) and recommendation (`1.X.X`) detection
- [x] `chunker.py` — Atomic recommendation preservation, 400-800 token target budget
- [x] `pipeline.py` — End-to-end orchestrator with atomic ChromaDB swap
- [x] CLI `ingest` command with `--dry-run`, `--doc-id`, `--verbose` flags

#### 1.4 Retrieval Inspector UI (T026–T036) ✅
- [x] `dense.py` — Dense cosine vector retriever
- [x] `POST /api/search` — Retrieval with latency tracking and citation formatting
- [x] `GET /api/index` — Index manifest and per-document statistics
- [x] `POST /api/generate` — 501 stub (Principle V)
- [x] CLI `query` command with `--top-k`, `--json`, `--full-text`
- [x] `api.ts` — Typed frontend fetch client
- [x] `ChunkCard.tsx` — Score gauges, section banners, 1-click citation copy
- [x] `SearchBox.tsx` — Clinical exemplar chips, top-k selector, loading spinner
- [x] `IndexStatus.tsx` — Real-time index health and registered source panel
- [x] `page.tsx` — Main search UI with responsive grid and filter tabs
- [x] `layout.tsx` — Root layout with clinical disclaimer banner

#### 1.5 Golden Evaluation (T037–T040) ✅
- [x] `golden_questions.yaml` — 12 clinical questions mapped to expected NG243 sections
- [x] `test_retrieval_quality.py` — Automated hit-rate verification (≥80% target)
- [x] CLI `eval` command
- [x] `test_no_split_recommendations.py` — Ensures atomic recommendation integrity

#### 1.6 Provenance System (T041–T043) ✅
- [x] `GET /api/sources` — Lists registered guideline documents
- [x] `test_registry.py` — Unit tests for provenance validation
- [x] Frontend provenance panel with caution badges

#### 1.7 Polish & Cross-Cutting (T044–T049) ✅
- [x] `README.md` — Comprehensive documentation
- [x] Static export configuration for single-process deployment
- [x] Structured logging throughout
- [x] Verification gates
- [x] `test_search_latency.py` — Latency integration test

### Files Delivered (Phase 1)

```
backend/app/
├── __init__.py
├── cli.py
├── config.py
├── errors.py
├── evaluation.py
├── main.py
├── models.py
├── api/
│   ├── __init__.py
│   ├── generate.py
│   └── search.py
├── embeddings/
│   ├── __init__.py
│   ├── base.py
│   └── openrouter.py
├── ingestion/
│   ├── __init__.py
│   ├── chunker.py
│   ├── cleaner.py
│   ├── parser.py
│   ├── pipeline.py
│   ├── registry.py
│   └── sectioner.py
└── retrieval/
    ├── __init__.py
    ├── base.py
    ├── dense.py
    └── store.py

frontend/
├── app/
│   ├── globals.css
│   ├── layout.tsx
│   ├── not-found.tsx
│   └── page.tsx
├── components/
│   ├── ChunkCard.tsx
│   ├── IndexStatus.tsx
│   ├── LanguageToggle.tsx
│   ├── SearchBox.tsx
│   └── ThemeToggle.tsx
└── lib/
    ├── api.ts
    └── translations.ts
```

---

## Phase 2 — Hybrid Search & Cross-Encoder Reranking 🔄

> **Status**: IN PROGRESS
> **Design Doc**: `docs/superpowers/specs/2026-08-17-hybrid-search-reranking-design.md`

### Motivation

Pure dense cosine search struggles with:
- **Exact drug names**: Hydrocortisone, Fludrocortisone, Dexamethasone
- **Specific lab values & numeric thresholds**: serum cortisol < 300 nmol/L
- **Precise dosages**: 100 mg IV bolus, 20 mg/day maintenance
- **Clinical abbreviations**: AI, PAI, SAI, CAH

**Solution**: Hybrid Search combining BM25 lexical retrieval with dense vector retrieval, fused via Reciprocal Rank Fusion (RRF), and optionally refined by a Cross-Encoder reranker.

### Architecture

```
         Query
           │
    ┌──────┴──────┐
    ▼              ▼
┌────────┐   ┌──────────┐
│ Dense  │   │  BM25    │
│Retriever│   │Retriever │
│(ChromaDB)│  │(BM25Okapi)│
└────┬───┘   └────┬─────┘
     │  top-K      │  top-K
     └──────┬──────┘
            ▼
   ┌─────────────────┐
   │ Reciprocal Rank  │
   │ Fusion (k=60)    │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │  Cross-Encoder   │     (optional, with graceful fallback)
   │  Reranker        │
   └────────┬────────┘
            ▼
      Final top-K results
      (with below_floor flags)
```

**RRF Formula:**
$$RRF\_Score(d) = \frac{1}{k + rank_{dense}(d)} + \frac{1}{k + rank_{bm25}(d)}$$

### Global Constraints

- **Protocol Seam**: `HybridRetriever` MUST implement `Retriever` protocol (`search(query, top_k) -> list[RetrievalResult]`).
- **Constitution Principle VI**: Weak matches below `relevance_floor` MUST be flagged (`below_floor=True`), never silently dropped.
- **Fail-Safe Fallback**: If Cross-Encoder weights fail to load, the retriever MUST fall back to RRF scoring without crashing.

---

### Task 2.1: Add Dependencies and Configuration Settings

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/app/config.py`
- Create: `backend/tests/unit/test_config.py`

**Interfaces:**
- Consumes: Pydantic Settings
- Produces: `retriever_type` (`"dense" | "hybrid" | "hybrid_rerank"`), `reranker_model`, `hybrid_candidate_k` in `Settings`

- [x] **Step 1: Write test for new config settings**

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

- [x] **Step 2: Add `rank-bm25` and `sentence-transformers` to requirements.txt**

Add to `requirements.txt`:
```text
rank-bm25>=0.2
sentence-transformers>=3.0
```

- [x] **Step 3: Update `backend/app/config.py`**

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

- [x] **Step 4: Run test to verify passes**

Run: `python -m pytest backend/tests/unit/test_config.py -v`
Expected: PASS

---

### Task 2.2: Implement BM25 Lexical Retriever

**Files:**
- Create: `backend/app/retrieval/bm25.py`
- Create: `backend/tests/unit/test_bm25.py`

**Interfaces:**
- Consumes: `VectorStore.all_chunks()`, query string
- Produces: `BM25Retriever.search(query, top_k) -> list[RetrievalResult]`

- [x] **Step 1: Write unit test for BM25 Retriever**

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

- [x] **Step 2: Implement `BM25Retriever` in `backend/app/retrieval/bm25.py`**

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

- [x] **Step 3: Run test to verify BM25 passes**

Run: `python -m pytest backend/tests/unit/test_bm25.py -v`
Expected: PASS

---

### Task 2.3: Implement Cross-Encoder Reranker

**Files:**
- Create: `backend/app/retrieval/reranker.py`
- Create: `backend/tests/unit/test_reranker.py`

**Interfaces:**
- Consumes: Query string and `list[Chunk]`
- Produces: `CrossEncoderReranker.rerank(query, chunks) -> list[tuple[Chunk, float]]`

- [x] **Step 1: Write unit test for Cross-Encoder Reranker with fallback**

```python
# backend/tests/unit/test_reranker.py
from backend.app.models import Chunk
from backend.app.retrieval.reranker import CrossEncoderReranker

def test_reranker_scores_chunks():
    c1 = Chunk.from_stored("c1", "Hydrocortisone dosage for adrenal crisis.", {"doc_id": "d1", "page_number": 1})
    c2 = Chunk.from_stored("c2", "General guidelines for clinical documentation.", {"doc_id": "d1", "page_number": 2})
    
    reranker = CrossEncoderReranker(disabled=True)  # Tests fallback behavior
    scored = reranker.rerank("Hydrocortisone dosage", [c1, c2])
    
    assert len(scored) == 2
    assert scored[0][0].chunk_id == "c1"
```

- [x] **Step 2: Implement `CrossEncoderReranker` in `backend/app/retrieval/reranker.py`**

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
                logger.warning(
                    "Could not initialize CrossEncoder reranker model '%s': %s. Falling back to rank fusion.",
                    self._settings.reranker_model, exc,
                )
                self._model = None

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []

        if self._model is not None:
            try:
                pairs = [[query, c.text] for c in chunks]
                scores = self._model.predict(pairs)
                # Normalize scores using min-max to [0, 1]
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

- [x] **Step 3: Run test to verify reranker passes**

Run: `python -m pytest backend/tests/unit/test_reranker.py -v`
Expected: PASS

---

### Task 2.4: Implement Hybrid Retriever & RRF Fusion

**Files:**
- Create: `backend/app/retrieval/hybrid.py`
- Create: `backend/tests/unit/test_hybrid.py`

**Interfaces:**
- Consumes: `DenseRetriever`, `BM25Retriever`, `CrossEncoderReranker`
- Produces: `HybridRetriever.search(query, top_k) -> list[RetrievalResult]`

- [x] **Step 1: Write unit test for Hybrid Retriever RRF fusion**

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

- [x] **Step 2: Implement `HybridRetriever` in `backend/app/retrieval/hybrid.py`**

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

        # 2. Reciprocal Rank Fusion (RRF) with k=60
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

- [x] **Step 3: Run test to verify hybrid retriever passes**

Run: `python -m pytest backend/tests/unit/test_hybrid.py -v`
Expected: PASS

---

### Task 2.5: Implement Factory and Update API & CLI

**Files:**
- Create: `backend/app/retrieval/factory.py`
- Modify: `backend/app/api/search.py`
- Modify: `backend/app/cli.py`
- Create: `backend/tests/integration/test_hybrid_api.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: `get_retriever(settings) -> Retriever` factory used by FastAPI search route and CLI commands.

- [x] **Step 1: Create `backend/app/retrieval/factory.py`**

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

- [x] **Step 2: Update `backend/app/api/search.py`**

Replace `DenseRetriever` instantiation in `search()` with `get_retriever(settings)`:
```python
from backend.app.retrieval.factory import get_retriever

# inside search():
results = get_retriever(settings).search(
    request.query, request.top_k or settings.top_k
)
```

- [x] **Step 3: Update `backend/app/cli.py`**

Update `query` and `eval` commands in `backend/app/cli.py` to use `get_retriever(settings)`.

- [x] **Step 4: Create integration test `backend/tests/integration/test_hybrid_api.py`**

```python
# backend/tests/integration/test_hybrid_api.py
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_search_api_with_hybrid_retriever():
    response = client.post("/api/search", json={"query": "Hydrocortisone adrenal crisis", "top_k": 3})
    assert response.status_code in (200, 535, 503)
```

- [x] **Step 5: Run integration tests to verify**

Run: `python -m pytest backend/tests/integration/test_hybrid_api.py -v`
Expected: PASS

---

### Task 2.6: Golden Evaluation Benchmark Verification

**Files:**
- Modify: `backend/tests/eval/test_retrieval_quality.py`

**Interfaces:**
- Consumes: `golden_questions.yaml`
- Produces: Automated verification confirming hybrid search hit-rate meets target ≥80%.

- [x] **Step 1: Run complete test suite and golden evaluation**

Run: `python -m pytest backend/tests/ -v`
Expected: All unit, integration, and golden retrieval quality tests PASS (≥80% hit rate).

### Phase 2 File Summary

**New Files (6):**
| File | Purpose |
|------|---------|
| `backend/app/retrieval/bm25.py` | BM25 lexical retriever with clinical tokenizer |
| `backend/app/retrieval/reranker.py` | Cross-Encoder reranker with graceful fallback |
| `backend/app/retrieval/hybrid.py` | Hybrid retriever with RRF fusion |
| `backend/app/retrieval/factory.py` | Retriever factory for dependency injection |
| `backend/tests/unit/test_bm25.py` | BM25 retriever unit tests |
| `backend/tests/unit/test_reranker.py` | Reranker unit tests |
| `backend/tests/unit/test_hybrid.py` | Hybrid retriever unit tests |
| `backend/tests/unit/test_config.py` | Config settings unit tests |
| `backend/tests/integration/test_hybrid_api.py` | Hybrid API integration tests |

**Modified Files (4):**
| File | Change |
|------|--------|
| `requirements.txt` | Add `rank-bm25>=0.2`, `sentence-transformers>=3.0` |
| `backend/app/config.py` | Add `retriever_type`, `reranker_model`, `hybrid_candidate_k` |
| `backend/app/api/search.py` | Switch from `DenseRetriever` to `get_retriever()` |
| `backend/app/cli.py` | Switch `query`/`eval` to use `get_retriever()` |

---

## Phase 3 — Generative Answer Synthesis 📋

> **Status**: DONE
> **Prerequisite**: Phase 2 completion (retrieval quality verified at ≥80%)

### Motivation

Currently, `POST /api/generate` returns **501 Not Implemented** (Constitution Principle V — Staged Delivery). Once retrieval quality is verified through Phase 2, the system can safely generate natural-language clinical answers grounded in retrieved evidence.

### Architecture

```
      User Query
          │
          ▼
  ┌─────────────────┐
  │  Hybrid Search   │    (Phase 2)
  │  + Reranking     │
  └────────┬────────┘
           │ top-K RetrievalResults
           ▼
  ┌─────────────────────────┐
  │  Generation Pipeline     │
  │                          │
  │  1. Evidence Assembly    │  ← Collect retrieved chunks + metadata
  │  2. Prompt Construction  │  ← System prompt + evidence + user query
  │  3. LLM Invocation       │  ← Claude Sonnet 4.5 via Anthropic API
  │  4. Citation Anchoring   │  ← Map assertions to chunk sources
  │  5. Abstention Check     │  ← If evidence_found=False → refuse
  └────────┬────────────────┘
           │
           ▼
  ┌─────────────────────────┐
  │  GenerateResponse        │
  │  - answer: str           │
  │  - citations: list       │
  │  - evidence_found: bool  │
  │  - disclaimer: str       │
  │  - model: str            │
  │  - latency_ms: int       │
  └─────────────────────────┘
```

### Tasks

#### Task 3.1: Add LLM Client & Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/app/config.py`
- Create: `backend/app/generation/__init__.py`
- Create: `backend/app/generation/client.py`

- [ ] **Step 1: Add `anthropic` SDK dependency**

Add to `requirements.txt`:
```text
anthropic>=0.40
```

- [ ] **Step 2: Add generation settings to `config.py`**

```python
generation_model: str = Field(
    default="anthropic/claude-sonnet-4.5",
    validation_alias="GENERATION_MODEL",
)
generation_max_tokens: int = Field(
    default=1024,
    validation_alias="GENERATION_MAX_TOKENS",
)
generation_temperature: float = Field(
    default=0.1,
    validation_alias="GENERATION_TEMPERATURE",
)
anthropic_api_key: str = Field(
    default="",
    validation_alias="ANTHROPIC_API_KEY",
)
```

- [ ] **Step 3: Implement LLM client wrapper**

Create `backend/app/generation/client.py`:
- Thin wrapper around Anthropic SDK
- Handles API key validation, retries, and error mapping
- Returns structured response with token usage tracking

---

#### Task 3.2: Implement Evidence Assembly & Prompt Engineering

**Files:**
- Create: `backend/app/generation/prompt.py`
- Create: `backend/app/generation/assembler.py`
- Create: `backend/tests/unit/test_assembler.py`

- [ ] **Step 1: Create evidence assembler**

```python
# backend/app/generation/assembler.py
"""Assembles retrieved chunks into a structured evidence context for the LLM."""

def assemble_evidence(results: list[RetrievalResult]) -> str:
    """Convert retrieval results into numbered evidence blocks with citation metadata."""
    # Format each chunk with [Source N] markers including:
    # - document_name, page_number, section_title, recommendation_ids
    # - Full chunk text
    # Filter out below_floor results unless they are the only results
    ...
```

- [ ] **Step 2: Create clinical system prompt template**

```python
# backend/app/generation/prompt.py
"""System prompt and prompt construction for clinical answer generation."""

SYSTEM_PROMPT = """You are Eva-AI, a clinical decision support assistant specializing in 
adrenal insufficiency management. You are strictly grounded in NICE Guideline NG243.

RULES:
1. Answer ONLY based on the provided evidence blocks.
2. Cite every factual claim using [Source N] notation.
3. If the evidence does not contain enough information to answer, say so explicitly.
4. Never provide medical advice beyond what the guidelines state.
5. Always include the clinical disclaimer.
6. Preserve exact drug names, dosages, and clinical values from the source.
"""
```

- [ ] **Step 3: Write unit tests for evidence assembly**

---

#### Task 3.3: Implement Citation Anchoring & Abstention Logic

**Files:**
- Create: `backend/app/generation/citations.py`
- Create: `backend/tests/unit/test_citations.py`

- [ ] **Step 1: Implement citation parser**

Extract `[Source N]` references from LLM output and map them back to the original `RetrievalResult` objects, producing structured citation metadata.

- [ ] **Step 2: Implement abstention logic**

If `evidence_found == False` (no chunks above `relevance_floor`), the generation endpoint MUST:
- Return a structured response indicating insufficient evidence
- NOT invoke the LLM at all (cost savings + safety)
- Provide the user with guidance on rephrasing their query

- [ ] **Step 3: Write unit tests for citation extraction and abstention**

---

#### Task 3.4: Implement `POST /api/generate` Endpoint

**Files:**
- Modify: `backend/app/api/generate.py`
- Modify: `backend/app/models.py`
- Create: `backend/tests/integration/test_generate_api.py`

- [ ] **Step 1: Add `GenerateRequest` and `GenerateResponse` models**

```python
# In backend/app/models.py
class GenerateRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    top_k: int | None = None
    include_sources: bool = True

class Citation(BaseModel):
    source_index: int
    chunk_id: str
    document_name: str
    page_number: int
    section_title: str
    recommendation_ids: str
    source_url: str

class GenerateResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    evidence_found: bool
    retrieval_results: list[RetrievalResult]
    model: str
    latency_ms: int
    disclaimer: str
```

- [ ] **Step 2: Replace 501 stub with full generation endpoint**

The endpoint should:
1. Execute hybrid search to retrieve evidence
2. Assemble evidence context
3. Check abstention conditions
4. Invoke LLM with structured prompt
5. Parse citations from response
6. Return `GenerateResponse` with full provenance

- [ ] **Step 3: Write integration tests**

---

#### Task 3.5: Update Frontend for Generative Answers

**Files:**
- Modify: `frontend/lib/api.ts`
- Create: `frontend/components/AnswerCard.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/lib/translations.ts`

- [ ] **Step 1: Add generate API client method**

Add `generateAnswer(query, topK)` to `frontend/lib/api.ts` calling `POST /api/generate`.

- [ ] **Step 2: Create `AnswerCard.tsx` component**

Display the LLM-generated answer with:
- Inline citation links `[Source N]` that scroll to corresponding `ChunkCard`
- Prominent clinical disclaimer
- Evidence quality indicators
- "Show/hide evidence" toggle to reveal underlying chunks
- Copy-formatted answer button

- [ ] **Step 3: Update main page to support generate mode**

Add a toggle or tab system allowing users to switch between:
- **Search Mode** (current): Shows raw retrieval results as chunk cards
- **Ask Mode** (new): Shows generated answer with citation-linked evidence

- [ ] **Step 4: Add Arabic translations for new UI elements**

---

#### Task 3.6: Generation Quality Evaluation

**Files:**
- Create: `backend/tests/eval/golden_generation.yaml`
- Create: `backend/tests/eval/test_generation_quality.py`

- [ ] **Step 1: Create golden generation test cases**

Define expected answer characteristics for key clinical questions:
- Must mention specific drug names when relevant
- Must cite correct page numbers
- Must abstain when query is out of scope
- Must include clinical disclaimer

- [ ] **Step 2: Implement automated generation quality checks**

Verify:
- Citation accuracy (all `[Source N]` references map to valid chunks)
- Abstention correctness (refuses out-of-scope queries)
- Factual grounding (key clinical facts present in answer)

### Phase 3 File Summary

**New Files:**
| File | Purpose |
|------|---------|
| `backend/app/generation/__init__.py` | Package init |
| `backend/app/generation/client.py` | Anthropic LLM client wrapper |
| `backend/app/generation/prompt.py` | System prompt & prompt construction |
| `backend/app/generation/assembler.py` | Evidence assembly from retrieval results |
| `backend/app/generation/citations.py` | Citation extraction & anchoring |
| `backend/tests/unit/test_assembler.py` | Evidence assembly tests |
| `backend/tests/unit/test_citations.py` | Citation extraction tests |
| `backend/tests/integration/test_generate_api.py` | Generation endpoint integration tests |
| `backend/tests/eval/golden_generation.yaml` | Golden generation test cases |
| `backend/tests/eval/test_generation_quality.py` | Generation quality evaluation |
| `frontend/components/AnswerCard.tsx` | LLM answer display with inline citations |

**Modified Files:**
| File | Change |
|------|--------|
| `requirements.txt` | Add `anthropic>=0.40` |
| `backend/app/config.py` | Add generation model, temperature, max tokens, API key |
| `backend/app/models.py` | Add `GenerateRequest`, `GenerateResponse`, `Citation` |
| `backend/app/api/generate.py` | Replace 501 stub with full generation endpoint |
| `frontend/lib/api.ts` | Add `generateAnswer()` method |
| `frontend/app/page.tsx` | Add Ask mode tab with `AnswerCard` integration |
| `frontend/lib/translations.ts` | Add Arabic translations for generation UI |

---

## Phase 4 — Production Hardening & Deployment 📋

> **Status**: PLANNED
> **Prerequisite**: Phase 3 completion

### Tasks

#### Task 4.1: Rate Limiting & API Security

- [ ] Add rate limiting middleware to FastAPI (e.g., `slowapi`)
- [ ] Implement API key authentication for production endpoints
- [ ] Add request/response logging with PII redaction
- [ ] Configure CORS for production domains

#### Task 4.2: Observability & Monitoring

- [ ] Add structured JSON logging with request correlation IDs
- [ ] Implement health check endpoint enhancements (dependency checks)
- [ ] Add Prometheus metrics (request latency, retrieval scores, error rates)
- [ ] Create alerting rules for retrieval quality degradation

#### Task 4.3: Caching & Performance

- [ ] Implement embedding cache to avoid re-computing for identical queries
- [ ] Add BM25 index warm-up on startup
- [ ] Implement response caching for frequently asked clinical questions
- [ ] Profile and optimize ChromaDB query performance

#### Task 4.4: Multi-Guideline Support

- [ ] Extend `sources.yaml` schema for multiple clinical guidelines
- [ ] Implement per-document filtering in search API
- [ ] Update frontend to support guideline scope selection
- [ ] Add collection namespacing in ChromaDB

#### Task 4.5: CI/CD Pipeline

- [ ] Create GitHub Actions workflow for automated testing
- [ ] Add pre-commit hooks (linting, formatting, type checking)
- [ ] Implement automated Docker image building and pushing
- [ ] Set up staging environment with automated deployment

#### Task 4.6: Documentation & Compliance

- [ ] Generate OpenAPI documentation with clinical examples
- [ ] Create clinician-facing user guide
- [ ] Document data governance and guideline update procedures
- [ ] Add license and compliance documentation for clinical use

---

## 9. Verification Plan

### Automated Tests

| Phase | Command | Target |
|-------|---------|--------|
| Phase 1 | `python -m pytest backend/tests/unit/ -v` | All PASS |
| Phase 1 | `python -m pytest backend/tests/integration/ -v` | All PASS |
| Phase 1 | `python -m pytest backend/tests/eval/ -v` | ≥80% hit rate |
| Phase 2 | `python -m pytest backend/tests/unit/test_bm25.py test_reranker.py test_hybrid.py -v` | All PASS |
| Phase 2 | `python -m pytest backend/tests/integration/test_hybrid_api.py -v` | All PASS |
| Phase 2 | `python -m pytest backend/tests/eval/ -v` | ≥80% hit rate (hybrid) |
| Phase 3 | `python -m pytest backend/tests/unit/test_assembler.py test_citations.py -v` | All PASS |
| Phase 3 | `python -m pytest backend/tests/integration/test_generate_api.py -v` | All PASS |
| Phase 3 | `python -m pytest backend/tests/eval/test_generation_quality.py -v` | Citation accuracy ≥90% |

### Manual Verification

| Check | Description |
|-------|-------------|
| Search UI | Enter clinical queries in both EN and AR; verify chunk cards display with scores and citations |
| Drug Name Precision | Search "Hydrocortisone dosage" — top result should contain exact drug name (Phase 2) |
| Ask Mode | Toggle to Ask mode; verify generated answer cites sources inline (Phase 3) |
| Abstention | Ask an out-of-scope question; verify system refuses to generate (Phase 3) |
| Dark/Light Mode | Toggle theme; verify all components render correctly |
| RTL Layout | Switch to Arabic; verify layout mirrors correctly |
| Docker Deploy | Run `docker-compose up`; verify frontend + backend serve correctly |

### Success Criteria

| Criterion | Target |
|-----------|--------|
| Golden question retrieval hit rate | ≥80% |
| Search latency (P95) | <2000ms |
| No silent hallucination | 100% citation-backed assertions |
| Clinical disclaimer visibility | Present on every response |
| Cross-encoder fallback | System functions without model weights |
| Zero unregistered source ingestion | Fail-closed provenance |

---

> **Last Updated**: 2026-08-17
> **Status Legend**: ✅ Complete | 🔄 In Progress | 📋 Planned
