# Clinical Decision Support Lite

> This system helps **clinicians and clinical trainees** answer questions about
> **adrenal insufficiency identification and management** using **NICE guideline NG243**.

A retrieval-augmented clinical decision support prototype that answers **only** from
official guideline PDFs, with every result traceable to a document, page, and section.

**Day 1 scope: ingestion and retrieval.** Answer generation is deliberately not
implemented — `POST /api/generate` returns `501` by design. See
[Constitution Principle V](.specify/memory/constitution.md).

---

## Status

| | |
|---|---|
| Corpus | NICE NG243 (2024), 63 pages |
| Index | 95 chunks · `gemini/gemini-embedding-001` · 3072-dim · ChromaDB |
| Retrieval quality | **12/12 golden questions (100%)**, mean rank 1.4 |
| Tests | 84 passing |

---

## Architecture

Monolithic repository, two processes in development, one deployable in production.

```text
             ┌─────────────────────┐
   Browser ─▶│  Next.js  :3000     │  retrieval inspector
             │  /api/* ──rewrite──▶│
             └──────────┬──────────┘
                        ▼
             ┌─────────────────────┐
             │  FastAPI  :8010     │  /api/search /index /sources /health
             └──────────┬──────────┘
                        ▼
        ┌───────────────┴────────────────┐
        ▼                                ▼
  ChromaDB (data/index)          OmniRoute gateway
  vectors + metadata             embeddings
```

**Ingestion pipeline**

```text
registry ─▶ parse ─▶ clean ─▶ section ─▶ chunk ─▶ embed ─▶ index ─▶ manifest
```

| Stage | Module | What it does |
|---|---|---|
| registry | `ingestion/registry.py` | Fail-closed provenance check; refuses unregistered PDFs |
| parse | `ingestion/parser.py` | PyMuPDF span extraction preserving page numbers and font size |
| clean | `ingestion/cleaner.py` | Frequency-based header/footer removal, glyph and hyphen repair |
| section | `ingestion/sectioner.py` | Detects `N.N` sections and `N.N.N` recommendations |
| chunk | `ingestion/chunker.py` | Packs blocks to ~600 tokens; recommendations stay atomic |
| embed | `embeddings/openrouter.py` | Batched, retrying, OpenAI-compatible gateway client |
| index | `retrieval/store.py` | Atomic build-then-swap into ChromaDB with metadata |

Two protocols exist as substitution seams for Day 2: `retrieval/base.py` (for hybrid
search or reranking) and `embeddings/base.py` (for a different provider). Everything
else is direct and concrete.

---

## Setup

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
cd frontend && npm install
```

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.

> **Provider note.** Despite the `OPENROUTER_*` variable names, this project points at
> an **OmniRoute** gateway (`https://omniroute.dawrly.space/v1`). OmniRoute is
> OpenAI-compatible, so the client works unchanged. The names are a known misnomer —
> see [research.md D3a](specs/001-clinical-rag-ingestion/research.md).
>
> The embedding model must be one your gateway holds upstream credentials for. On this
> instance `openai/*` and `openrouter/*` are unauthenticated; `gemini/*` works.

---

## Usage

Validate parsing and chunking with no API spend:

```bash
python -m backend.app.cli ingest --dry-run --verbose
```

Build the index:

```bash
python -m backend.app.cli ingest
```

Query from the terminal:

```bash
python -m backend.app.cli query "How should an adrenal crisis be managed?"
```

Measure retrieval quality against the golden set:

```bash
python -m backend.app.cli eval
```

### Run the app

Backend (port 8010 — 8000 is blocked on some Windows setups):

```bash
python -m uvicorn backend.app.main:app --reload --port 8010
```

Frontend, in a second terminal:

```bash
cd frontend && npm run dev
```

Open http://localhost:3000. Override the proxy target with `BACKEND_URL` if needed.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/search` | Top-K retrieval with scores and full citation metadata |
| `GET /api/index` | Index manifest: model, dimensions, chunk counts |
| `GET /api/sources` | Provenance registry with credibility justifications |
| `GET /api/health` | Liveness and index readiness |
| `POST /api/generate` | **501 by design** — Day 1 stops before generation |

Full schemas: [`contracts/search-api.yaml`](specs/001-clinical-rag-ingestion/contracts/search-api.yaml).

---

## Tests

```bash
python -m pytest backend/tests/ -v
```

Unit tests cover the three deterministic transforms. Integration tests run the real
NG243 ingest with a stubbed embedder — no API key needed. The golden-set and latency
suites skip automatically when no index or key is present.

---

## Design decisions worth knowing

**Recommendations are atomic.** A numbered clinical recommendation is never split
across chunks. Splitting one mid-sentence yields a chunk that is both incoherent and
clinically partial. An oversized recommendation is emitted whole and flagged, never
truncated — truncation can invert a recommendation's meaning.

**Sub-section boundaries are hard.** NG243 separates "People aged 16 and over" from
"Children and young people". Packing across that boundary to hit a token target would
put adult and paediatric dosing in one chunk. Mean chunk size is 190 tokens rather than
the nominal 400 floor as a direct result, and that is the correct trade
([research.md D6a](specs/001-clinical-rag-ingestion/research.md)).

**Weak results are shown, not hidden.** Anything below the relevance floor is returned
and flagged. Silently filtering would hide exactly the failure modes you need to see.

**Metadata lives on the vector.** Citation fields are stored in the ChromaDB entry, not
a sidecar file that can drift out of sync.

---

## Project layout

```text
backend/app/         FastAPI app, ingestion pipeline, retrieval, CLI
backend/tests/       unit · integration · eval
frontend/            Next.js retrieval inspector
data/corpus/         registered guideline PDFs
data/sources.yaml    provenance registry
data/index/          ChromaDB (gitignored; rebuild with ingest)
specs/001-.../       spec, plan, research, data model, contracts, tasks
.specify/memory/     project constitution
```

---

## Not in scope

Answer generation, prompt engineering, hybrid search, reranking, live PDF upload,
authentication, OCR, and any clinical topic beyond adrenal insufficiency.
