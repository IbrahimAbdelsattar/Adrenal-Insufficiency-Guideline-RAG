# Implementation Plan: Clinical Guideline Ingestion & Retrieval Baseline

**Branch**: `001-clinical-rag-ingestion` | **Date**: 2026-08-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-clinical-rag-ingestion/spec.md`

## Summary

Build a monolithic clinical RAG application — FastAPI backend, Next.js frontend, single
repository — and implement it through the first working vector index.

A CLI ingest command reads registered guideline PDFs from `data/corpus/`, parses them
with PyMuPDF while preserving page numbers, strips repeated headers/footers and glyph
corruption, detects the NICE numbered-recommendation hierarchy, packs whole
recommendations into 400–800 token section-aware chunks, embeds them via OpenRouter
(`openai/text-embedding-3-small`), and writes them to a persistent embedded ChromaDB
collection with full citation metadata stored on each vector entry.

A `/api/search` endpoint and a Next.js retrieval inspector expose the results:
question → ranked chunks → score, document, page, section, text. A pytest golden-set
suite measures top-K hit rate so Day 2 tuning is comparable.

Generation is architected as an interface contract and deliberately left unimplemented,
per Constitution Principle V.

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5.x on Node 24 (frontend)

**Primary Dependencies**:
- Backend: FastAPI, Uvicorn, PyMuPDF, ChromaDB, httpx, pydantic v2, pydantic-settings,
  tiktoken, PyYAML
- Frontend: Next.js 15 (App Router), React 19, Tailwind CSS
- Model provider: OpenRouter (OpenAI-compatible `/api/v1/embeddings` and
  `/api/v1/chat/completions`)

**Storage**: ChromaDB embedded, persisted to `data/index/`. Corpus PDFs and
`data/sources.yaml` on the filesystem. No relational database.

**Testing**: pytest for unit, integration, and the golden-question retrieval suite

**Target Platform**: Local development on Windows/macOS/Linux; single-host deployment

**Project Type**: Web application — monolithic repository, two processes in development,
one deployable artifact in production

**Performance Goals**: Full corpus ingest under 10 minutes. Search response under 3
seconds end to end.

**Constraints**: Single model provider (one API key). No GPU. No Docker required. No
authentication. Index must survive process restart.

**Scale/Scope**: 1 source document (NICE NG243, 63 pages), roughly 150–350 chunks, single
concurrent user, ~10 evaluation questions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| # | Principle | Gate | Initial | Post-Design |
|---|---|---|---|---|
| I | Evidence-Grounded Answers Only | No generation path exists that can bypass retrieval | ✅ PASS — generation unimplemented; contract mandates abstention below the relevance floor | ✅ PASS |
| II | Citation Metadata Is Structural | Metadata stored on the vector entry, returned with score in one call | ✅ PASS — ChromaDB native metadata; no sidecar file anywhere in the design | ✅ PASS |
| III | Source Legitimacy and Provenance | Every source registered with publisher, year, URL, type, justification | ✅ PASS — `sources.yaml` required; ingest fails on unregistered PDFs | ✅ PASS |
| IV | Narrow Scope Discipline | One clinical topic, scope statement written before code | ✅ PASS — adrenal insufficiency, single source NG243; disclaimer required in UI | ✅ PASS |
| V | Staged Delivery | Retrieval complete and verified before generation work | ✅ PASS — generation is an interface contract with no implementation | ✅ PASS |
| VI | Human Verification Over Automated Confidence | Chunk inspection and page trace-back are explicit deliverables | ✅ PASS — inspector UI plus manual gates in spec; weak results never hidden | ✅ PASS |

**Result: PASS — no violations. Complexity Tracking is empty.**

## Project Structure

### Documentation (this feature)

```text
specs/001-clinical-rag-ingestion/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── search-api.yaml      # OpenAPI: implemented endpoints
│   ├── generation-api.yaml  # OpenAPI: Day 2 contract, unimplemented
│   └── cli-contract.md      # Ingest / query / eval command contracts
└── tasks.md             # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, router mounting, static serving
│   ├── config.py                # pydantic-settings; all tunables, no magic numbers
│   ├── models.py                # Pydantic schemas shared across layers
│   ├── api/
│   │   ├── search.py            # POST /api/search, GET /api/health, GET /api/index
│   │   └── generate.py          # Day 2 stub — returns 501, contract-defined
│   ├── ingestion/
│   │   ├── registry.py          # Loads/validates data/sources.yaml
│   │   ├── parser.py            # PyMuPDF extraction, page-faithful spans
│   │   ├── cleaner.py           # Header/footer, glyph, hyphen, front-matter removal
│   │   ├── sectioner.py         # NICE 1.1 / 1.1.1 hierarchy detection
│   │   ├── chunker.py           # Atomic-recommendation packing to token budget
│   │   └── pipeline.py          # Orchestration; writes the index manifest
│   ├── retrieval/
│   │   ├── base.py              # Retriever protocol — the Day 2 swap seam
│   │   ├── dense.py             # Cosine top-K over ChromaDB
│   │   └── store.py             # ChromaDB client, collection lifecycle
│   ├── embeddings/
│   │   ├── base.py              # Embedder protocol
│   │   └── openrouter.py        # Batched OpenRouter embeddings client
│   └── cli.py                   # python -m backend.app.cli ingest|query|eval
└── tests/
    ├── unit/                    # cleaner, sectioner, chunker
    ├── integration/             # end-to-end ingest over a fixture PDF
    └── eval/
        ├── golden_questions.yaml
        └── test_retrieval_quality.py

frontend/
├── app/
│   ├── layout.tsx               # Shell, disclaimer banner
│   ├── page.tsx                 # Retrieval inspector
│   └── globals.css
├── components/
│   ├── SearchBox.tsx
│   ├── ChunkCard.tsx            # Score, document, page, section, text, source flags
│   └── IndexStatus.tsx
├── lib/api.ts                   # Typed client for the backend
├── next.config.ts               # Dev rewrite: /api/* -> :8000
└── package.json

data/
├── corpus/                      # Registered guideline PDFs
├── sources.yaml                 # Provenance registry
└── index/                       # ChromaDB persistence (gitignored)

.env.example
requirements.txt
README.md
```

**Structure Decision**: Monolithic repository, two runtime processes in development.
`backend/` is a single FastAPI application with the RAG pipeline as internal packages —
no microservices, no separate worker. `frontend/` is a Next.js app whose
`next.config.ts` rewrites `/api/*` to `http://localhost:8000` during development. For
production, the frontend builds to a static export served by FastAPI's `StaticFiles`,
yielding one deployable process.

The ingestion, retrieval, and embedding packages are separated behind protocols
(`retrieval/base.py`, `embeddings/base.py`) specifically so Day 2 can substitute hybrid
search or a reranker without touching `api/`. That is the only abstraction in the design;
everything else is direct and concrete, in service of prototype speed.

## Corpus Decision Record

| Document | Status | Rationale |
|---|---|---|
| NICE NG243 — *Adrenal insufficiency: identification and management* (2024-08-28, 63pp) | **Included** | Official NICE guideline, current, public, numbered recommendation structure ideal for section-aware chunking. |
| WHO Drug Information Vol 17 No.4 (2003) | **Excluded** | A periodical, not a clinical guideline; 23 years old; content spans ~30 unrelated topics. Fails Constitution Principle III. Dropped by owner decision on 2026-08-16. The file remains on disk but is unregistered, so ingestion will reject it. |

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
