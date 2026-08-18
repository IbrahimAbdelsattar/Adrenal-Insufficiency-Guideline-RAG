<!-- converted from Eva_AI_Comprehensive_Documentation.docx -->

Eva AI
Comprehensive Technical Blueprint & Non-Technical Executive Overview

# 1. Non-Technical Executive Overview
## 1.1 The Clinical Challenge
Adrenal insufficiency (including Primary Addison's Disease and Secondary Adrenal Suppression) is a life-threatening endocrine disorder requiring rapid, highly precise diagnosis, emergency adrenal crisis management, and strict sick-day dosing protocols. Clinicians and trainees face complex, multi-page clinical guidelines (such as NICE NG243, published August 2024), where looking up specific dosage adjustments or diagnostic criteria during clinical rounds can be time-consuming and error-prone.
## 1.2 What is Eva AI?
Eva AI (Clinical Decision Support Lite) is an advanced Retrieval-Augmented Generation (RAG) platform. Unlike generic AI chatbots that guess or synthesize answers with a risk of clinical hallucinations, Eva AI functions as a zero-hallucination evidence search engine. It ingests official clinical guideline PDFs, strips extraction noise while preserving page numbers, and retrieves the most relevant, un-altered clinical recommendation text.
## 1.3 Core Non-Technical Capabilities
- 100% Traceable Citations: Every answer card displays the document name, exact page number, section title, and recommendation ID (e.g. Rec 1.2.1).
- Atomic Recommendation Preservation: Clinical recommendations are never cut mid-sentence or split across chunks.
- Bilingual Internationalization: Seamless single-click switching between English and Arabic (dir=rtl) with full medical terms.
- Monomorphic Soft UI & Dual Themes: A tactile, extruded 3D design available in Light Mode and Dark Mode for high visual comfort.

# 2. System Constitution & Governance Principles
The architecture enforces six strict constitutional principles to guarantee clinical safety and strict regulatory compliance:

# 3. System Architecture & Component Topology
## 3.1 Topology & Runtime Processes
The platform is designed as a monolithic repository with clean internal component boundaries:
- Development Mode: Two concurrent processes — FastAPI backend running on port 8000 and Next.js 15 App Router running on port 3000 (with dev proxy rewrites for /api/*).
- Production Mode: Single deployable artifact where FastAPI serves the static frontend build export (frontend/out) via StaticFiles.
- Protocol Seams: Ingestion, Retrieval, and Embedding layers are behind explicit Python Protocols (retrieval/base.py & embeddings/base.py) allowing seamless Day 2 swap for hybrid search or cross-encoder rerankers.
## 3.2 Technology Stack Matrix

# 4. RAG Ingestion Pipeline & Algorithmic Mechanics
The ingestion pipeline converts multi-page clinical guideline PDFs into section-aware, citation-ready vector entries without losing clinical context. Below is the multi-stage transformation sequence:
## 4.1 Ingestion Pipeline Stages
- Fail-Closed Registry Check: Validates every PDF in data/corpus/ against data/sources.yaml. Unregistered PDFs immediately abort ingestion (Exit code 1).
- PyMuPDF Span Extraction: PyMuPDF (fitz) extracts text spans while preserving font size, font weight, and 1-indexed source PDF page numbers.
- Frequency-Based Cleaning: Lines appearing on >60% of pages (running footers, copyright notices) are automatically purged as boilerplate. Bullet glyphs and line-break hyphenations are repaired.
- Hierarchy Detection: Detects N.N major sections (e.g. 1.2 Initial identification) and N.N.N recommendation numbers (e.g. 1.2.1).
- Atomic Recommendation Packing: Treat each numbered recommendation as an ATOMIC unit that is never split across chunks. Consecutive sibling recommendations are packed into token budgets of 400–800 tokens (tiktoken cl100k_base). Oversized atomic recommendations are emitted whole and flagged.
- Batched Vector Embeddings: Generates 1536-dim embeddings via OpenRouter in batches of 100 with exponential backoff retries.
- Atomic Collection Swap: Updates ChromaDB collection atomically and writes manifest.json recording the embedding model, dimensions, build time, and document stats.

# 5. Eva AI Visual System & User Experience
## 5.1 Monomorphic Soft-UI (Neumorphic Dark/Light)
Eva AI introduces a custom Monomorphic Design System. Elements appear sculpted directly out of a single continuous canvas (#0D2440 in Dark Mode, #F0F5FA in Light Mode) using dual offset drop-shadows and debossed inner tracks.
## 5.2 Internationalization & Bilingual Arabic Support
The platform provides full bilingual English and Arabic support:
- Single-Click Language Toggle: Instant switching between English and Arabic (العربية).
- RTL Directionality: Full dir=rtl layout adaptations, font switching to Google Tajawal & Cairo for Arabic typography.
- Bilingual Translations: Complete medical terminology translation dictionary (translations.ts).

# 6. CLI Interface & API Specifications
## 6.1 Command Line Interface (backend.app.cli)
- ingest [--dry-run] [--doc-id DOC] [--verbose]: Rebuild vector index from data/corpus/.
- query "question" [--top-k K] [--json] [--full-text]: Execute retrieval query from shell.
- eval [--top-k K] [--json]: Execute golden question retrieval test suite.
## 6.2 Exit Codes Matrix
## 6.3 REST API Endpoint Specifications
- GET /api/health: Returns 200 OK with server status and index_ready boolean.
- POST /api/search: Accepts { query: string, top_k: int }, returns SearchResponse with ranked RetrievalResults, latency_ms, and disclaimer.
- GET /api/index: Returns IndexManifest metadata and document/chunk counts.
- GET /api/sources: Returns all registered SourceDocuments with credibility justifications.
- POST /api/generate: Returns 501 Not Implemented stub (Constitution Principle V).

# 7. Quality Evaluation & Validation Framework
Retrieval quality is benchmarked against a golden clinical question dataset (backend/tests/eval/golden_questions.yaml) containing 10+ clinical queries over NICE NG243 sections 1.1 through 1.8.

# 8. Operations & Quickstart
## 8.1 One-Click Windows Launch (start.bat)
Run start.bat from the repository root to automatically set up virtual environments, install dependencies, copy .env defaults, and launch both FastAPI (:8000) and Next.js (:3000) concurrently.
## 8.2 Manual Startup Commands
- python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
- cd frontend && npm install && cd ..
- python -m backend.app.cli ingest
- uvicorn backend.app.main:app --reload --port 8000
- cd frontend && npm run dev

— End of System Specification Document —
| Executive Summary & Clinical Scope Statement
This system helps clinicians and clinical trainees answer questions about adrenal insufficiency identification and management using NICE guideline NG243 and registered supporting official sources. Every retrieved chunk carries structural page-level citations, section titles, and recommendation numbers without automated hallucination. |
| --- |
| Principle | Clinical Rule & Implementation |
| --- | --- |
| I. Evidence Grounded | No generation path exists that can bypass retrieval. Answers must be strictly grounded in verified guideline text. |
| II. Structural Citations | Citation metadata (document, page, section, recommendation) is stored natively inside ChromaDB vector entries, returning in a single call. |
| III. Source Legitimacy | Fail-closed provenance registry (data/sources.yaml). Unregistered PDFs are rejected immediately prior to parsing. |
| IV. Scope Discipline | Strictly limited to adrenal insufficiency (NICE NG243). Persistent clinical decision-support disclaimers are rendered across UI and API. |
| V. Staged Delivery | Retrieval baseline verified via golden-set evaluation before introducing LLM generation (/api/generate returns 501 stub). |
| VI. Human Verification | Low-scoring chunks are flagged, never silently hidden. Every chunk provides explicit page-number trace-back to the source PDF. |
| Component Layer | Technology Selected | Architectural Rationale |
| --- | --- | --- |
| Backend Framework | FastAPI + Uvicorn (Python 3.13) | High performance async framework, automatic Pydantic v2 OpenAPI schema generation. |
| Vector Store | ChromaDB Persistent Client | Zero external server dependency; stores scalar citation metadata natively on vector entries. |
| Embedding Provider | OpenRouter (text-embedding-3-small) | 1536-dimensional embeddings, cost-efficient, single API key infrastructure. |
| Frontend Framework | Next.js 15 (React 19, TypeScript) | App Router, Tailwind CSS, Monomorphic Soft-UI design, bilingual English/Arabic RTL. |
| Exit Code | System Meaning |
| --- | --- |
| 0 | Success — Ingestion completed / Golden evaluation hit rate >= 80% |
| 1 | Unregistered PDF present in corpus directory (FR-002) |
| 2 | PDF has no extractable text layer (scanned PDF) |
| 3 | No sections detected in a guideline document |
| 4 | Embedding provider failure after exponential backoff retries |
| 5 | Configuration error (missing API key or invalid directory paths) |
| Quality Metric & Benchmark Goal
Target: Hit-rate >= 80% (at least 8 out of 10 clinical questions retrieve their expected guideline section within top-5 results). Evaluated automatically via pytest backend/tests/eval/. |
| --- |