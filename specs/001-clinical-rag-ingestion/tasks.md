---

description: "Task list for Clinical Guideline Ingestion & Retrieval Baseline"
---

# Tasks: Clinical Guideline Ingestion & Retrieval Baseline

**Input**: Design documents from `specs/001-clinical-rag-ingestion/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: Included. The specification explicitly requires them — FR-031, FR-032, FR-033 and User Story 3 mandate an automated golden-question retrieval suite. Unit tests are also included for the three deterministic transform modules (cleaner, sectioner, chunker) because SC-006 ("zero recommendations split across chunks") cannot be verified by inspection alone.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete work)
- **[Story]**: Owning user story (US1–US4)

## Path Conventions

Monolithic repository, per [plan.md](plan.md) Structure Decision. Backend Python under `backend/app/`, tests under `backend/tests/`, frontend Next.js under `frontend/`, data under `data/`. All paths below are repository-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, dependencies, configuration, corpus placement.

- [X] T001 Create the backend package tree with `__init__.py` files: `backend/app/{api,ingestion,retrieval,embeddings}/` and `backend/tests/{unit,integration,eval}/` per plan.md Source Code layout
- [X] T002 [P] Create `requirements.txt` pinning fastapi, uvicorn[standard], pymupdf, chromadb, httpx, pydantic>=2, pydantic-settings, tiktoken, pyyaml, pytest, pytest-asyncio
- [X] T003 [P] Create `.env.example` with all 15 configuration variables and their defaults from contracts/cli-contract.md Configuration contract; leave `OPENROUTER_API_KEY` empty
- [X] T004 [P] Create `.gitignore` excluding `.venv/`, `.env`, `data/index/`, `__pycache__/`, `frontend/node_modules/`, `frontend/.next/`
- [X] T005 Create `backend/app/config.py` with a pydantic-settings `Settings` class exposing every variable from contracts/cli-contract.md as a typed field with its documented default, plus a cached `get_settings()` accessor
- [X] T006 Create `data/corpus/` and move `adrenal-insufficiency-identification-and-management-pdf-66143954919877.pdf` into it; delete `17_4_2003.pdf` from the repository root (excluded per plan.md Corpus Decision Record)
- [X] T007 [P] Initialize the Next.js app in `frontend/` (App Router, TypeScript, Tailwind) and set `frontend/next.config.ts` to rewrite `/api/:path*` to `http://localhost:8000/api/:path*`

**Checkpoint**: `pip install -r requirements.txt` succeeds, `npm run dev` serves a blank page, `data/corpus/` holds exactly one PDF.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared schemas, provenance registry, provider clients, vector store, app shell. Every user story depends on these.

**⚠️ MUST complete before Phase 3.**

- [X] T008 [P] Define all Pydantic schemas in `backend/app/models.py` — `SourceDocument`, `Chunk`, `IndexManifest`, `RetrievalResult`, `SearchResponse`, `GoldenQuestion` — with the exact fields, types, and defaults from data-model.md; enforce the "no nulls, use empty string" rule required by ChromaDB metadata
- [X] T009 Create `data/sources.yaml` containing the NICE NG243 entry verbatim from data-model.md Registered corpus, including `credibility_note` and `license_note`
- [X] T010 Implement `backend/app/ingestion/registry.py` — load and validate `data/sources.yaml` into `SourceDocument` models, enforce unique `doc_id` matching `^[a-z0-9_]+$`, reject placeholder/empty `credibility_note`, compute `requires_caution` when `document_type != "guideline"` or `publication_year < current_year - 10`, and raise a fail-closed error naming any PDF in `data/corpus/` with no registry entry (FR-001, FR-002, FR-003)
- [X] T011 [P] Define the `Embedder` protocol in `backend/app/embeddings/base.py` with `embed_documents(list[str]) -> list[list[float]]`, `embed_query(str) -> list[float]`, and a `model_id` property
- [X] T012 Implement `backend/app/embeddings/openrouter.py` — an `Embedder` posting to `{OPENROUTER_BASE_URL}/embeddings`, batching inputs at `EMBEDDING_BATCH_SIZE`, retrying 429 and 5xx with exponential backoff, and raising a typed error that maps to CLI exit code 4 (research.md D3)
- [X] T013 [P] Define the `Retriever` protocol in `backend/app/retrieval/base.py` with `search(query: str, top_k: int) -> list[RetrievalResult]` — the Day 2 substitution seam (FR-035)
- [X] T014 Implement `backend/app/retrieval/store.py` — persistent ChromaDB client at `INDEX_DIR`, collection lifecycle with cosine space, atomic build-then-swap so a failed ingest leaves the previous index queryable, and read/write of `data/index/manifest.json` (FR-018, FR-020)
- [X] T015 Create the FastAPI app in `backend/app/main.py` — mount the API router, enable CORS for `localhost:3000`, and implement `GET /api/health` returning `status` and `index_ready` per contracts/search-api.yaml

**Checkpoint**: `uvicorn backend.app.main:app` starts and `GET /api/health` returns `{"status":"ok","index_ready":false}`.

---

## Phase 3: User Story 1 — Ingest a guideline corpus into a searchable index (Priority: P1) 🎯 MVP

**Goal**: One command turns registered PDFs into a persistent, fully-attributed vector index.

**Independent Test**: Run the ingest command; the vector store reports a non-zero chunk count and every chunk carries complete metadata.

### Tests for User Story 1

- [X] T016 [P] [US1] Unit-test the cleaner in `backend/tests/unit/test_cleaner.py` — boilerplate lines above `BOILERPLATE_PAGE_RATIO` are removed, `�` normalises to `- `, hyphenated line-break splits rejoin, dot-leader contents pages are detected as front matter (research.md D5)
- [X] T017 [P] [US1] Unit-test the sectioner in `backend/tests/unit/test_sectioner.py` — `N.N` sections and `N.N.N` recommendations are detected from NG243-shaped fixture text, prose sub-headings are captured, and section state carries across page boundaries
- [X] T018 [P] [US1] Unit-test the chunker in `backend/tests/unit/test_chunker.py` — no numbered recommendation is split across chunks (SC-006), chunks fall within 400–800 tokens unless `is_oversized`, oversized atomic recommendations are emitted whole and flagged rather than truncated (FR-014)
- [X] T019 [US1] Integration-test the pipeline in `backend/tests/integration/test_ingest_pipeline.py` — a fixture PDF ingests end to end with a stubbed embedder, producing chunks with all 15 metadata fields non-null, unique `chunk_id`s, and a written manifest

### Implementation for User Story 1

- [X] T020 [P] [US1] Implement `backend/app/ingestion/parser.py` — PyMuPDF `page.get_text("dict")` extraction yielding per-span text with font size, weight, and 1-indexed source page number; raise the typed no-text-layer error mapping to exit code 2 (FR-004, research.md D4)
- [X] T021 [P] [US1] Implement `backend/app/ingestion/cleaner.py` — frequency-based header/footer removal using `BOILERPLATE_PAGE_RATIO`, glyph normalisation, hyphenation repair, front-matter detection, and per-page empty-after-cleaning counting (FR-005 through FR-009)
- [X] T022 [US1] Implement `backend/app/ingestion/sectioner.py` — detect the `N.N` section and `N.N.N` recommendation hierarchy plus prose sub-headings using span font metadata and numbering regexes; raise the typed no-sections error mapping to exit code 3 (FR-010)
- [X] T023 [US1] Implement `backend/app/ingestion/chunker.py` — treat each numbered recommendation as atomic, pack same-section siblings toward `CHUNK_TARGET_TOKENS` within the min/max band using tiktoken `cl100k_base`, emit oversized recommendations whole with `is_oversized=true`, and assign `chunk_id` as `{doc_id}_p{page:02d}_c{seq:02d}` (FR-011 through FR-014, FR-016)
- [X] T024 [US1] Implement `backend/app/ingestion/pipeline.py` — orchestrate registry → parse → clean → section → chunk → embed → index, attach all denormalised metadata from `SourceDocument` to every chunk, write `IndexManifest` with the embedding model and per-document page statistics, and make the run idempotent (FR-015, FR-017, FR-019, FR-020)
- [X] T025 [US1] Implement the `ingest` command in `backend/app/cli.py` with `--dry-run`, `--doc-id`, and `--verbose`, emitting the progress output and the exit codes 0–5 defined in contracts/cli-contract.md

**Checkpoint**: `python -m backend.app.cli ingest` builds the index; quickstart V1 and V2 pass.

---

## Phase 4: User Story 2 — Inspect retrieval results for a clinical question (Priority: P1)

**Goal**: Question in, ranked chunks out, each showing score, document, page, section, and text — the end-of-day demo path.

**Independent Test**: Submit a question through the UI and see ranked chunks with complete, correct provenance on every card.

**Depends on**: Phase 3 (needs a populated index).

- [X] T026 [US2] Implement `backend/app/retrieval/dense.py` — a `Retriever` embedding the query, running cosine top-K against ChromaDB, converting distance to a 0–1 score, assigning ranks, and setting `below_floor` from `RELEVANCE_FLOOR` without ever removing results (FR-021, FR-022, FR-023)
- [X] T027 [US2] Implement `POST /api/search` in `backend/app/api/search.py` returning the `SearchResponse` from contracts/search-api.yaml — including `evidence_found`, `embedding_model`, `latency_ms`, and the disclaimer — with 422 on invalid query and 503 when the index is missing or the provider is unavailable (FR-024, FR-025)
- [X] T028 [US2] Implement `GET /api/index` in `backend/app/api/search.py` returning the `IndexManifest`, 404 when no index exists, and rejecting queries whose manifest embedding model differs from the configured one (FR-030, data-model.md validation rule)
- [X] T029 [P] [US2] Implement the `POST /api/generate` stub in `backend/app/api/generate.py` returning HTTP 501 with the explanatory message from contracts/generation-api.yaml (FR-034, Constitution Principle V)
- [X] T030 [P] [US2] Implement the `query` command in `backend/app/cli.py` with `--top-k`, `--json`, and `--full-text`, rendering the ranked output and `[BELOW FLOOR]` labels exactly as specified in contracts/cli-contract.md (FR-024)
- [X] T031 [P] [US2] Create the typed API client in `frontend/lib/api.ts` with TypeScript interfaces mirroring `SearchResponse`, `RetrievalResult`, `Chunk`, and `IndexManifest` from contracts/search-api.yaml
- [X] T032 [P] [US2] Build `frontend/components/ChunkCard.tsx` displaying relevance score, document name, page number, section title, sub-section, recommendation ids, and full chunk text; visibly flag `requires_caution` and `below_floor` results (FR-027, FR-028)
- [X] T033 [P] [US2] Build `frontend/components/SearchBox.tsx` — controlled input with submit, loading state, and error surface
- [X] T034 [P] [US2] Build `frontend/components/IndexStatus.tsx` showing document count, chunk count, and embedding model from `GET /api/index` (FR-030)
- [X] T035 [US2] Build `frontend/app/page.tsx` composing SearchBox, IndexStatus, and the ranked ChunkCard list; render an explicit "no evidence available" state when `evidence_found` is false or the index is empty (FR-026, US2 scenario 5)
- [X] T036 [US2] Build `frontend/app/layout.tsx` with the persistent decision-support disclaimer stating the system is not a diagnostic or emergency service (FR-029, Constitution Principle IV)

**Checkpoint**: quickstart V3, V4, V9, and V10 pass. **This is the demo gate: question → top chunks → source page and section.**

---

## Phase 5: User Story 3 — Verify retrieval quality against a golden question set (Priority: P2)

**Goal**: A repeatable, comparable measure of retrieval quality so Day 2 tuning is measured rather than guessed.

**Independent Test**: Run the evaluation and get a per-question pass/fail table plus an aggregate hit rate.

**Depends on**: Phase 4 (needs working retrieval).

- [X] T037 [US3] Author `backend/tests/eval/golden_questions.yaml` with at least 10 adrenal-insufficiency questions, each carrying `id`, `question`, `expected_doc_id`, `expected_sections`, optional `expected_recommendation_ids`, and a `notes` justification — derived by reading NG243 sections 1.1 through 1.8 (FR-031)
- [X] T038 [US3] Implement `backend/tests/eval/test_retrieval_quality.py` asserting that each golden question retrieves an expected section within top-K, and reporting per-question rank plus aggregate hit rate against the 80% target (FR-032, FR-033, SC-003)
- [X] T039 [US3] Implement the `eval` command in `backend/app/cli.py` with `--top-k` and `--json`, producing the HIT/MISS table, hit rate, mean rank of hits, and exit code 0/1 against the target from contracts/cli-contract.md
- [X] T040 [P] [US3] Add `backend/tests/integration/test_no_split_recommendations.py` verifying against the real built index that every recommendation id appears in exactly one chunk (SC-006, quickstart V8)

**Checkpoint**: quickstart V5 and V8 pass; hit rate ≥ 80%.

---

## Phase 6: User Story 4 — Confirm source provenance and credibility (Priority: P3)

**Goal**: Every corpus document's provenance is inspectable and complete.

**Independent Test**: Read the registry and confirm every corpus PDF has a complete, non-placeholder entry.

**Depends on**: Phase 2 (registry exists).

- [X] T041 [P] [US4] Implement `GET /api/sources` in `backend/app/api/search.py` returning all registered `SourceDocument` entries with publisher, year, URL, type, credibility note, and licence note per contracts/search-api.yaml (FR-001)
- [X] T042 [P] [US4] Add `backend/tests/unit/test_registry.py` asserting that an unregistered PDF in the corpus causes a fail-closed error naming the file, and that placeholder or empty credibility notes are rejected (FR-002, US4 scenario 2)
- [X] T043 [US4] Add a provenance panel to `frontend/app/page.tsx` listing each source with its publisher, publication year, and linked source URL

**Checkpoint**: quickstart V2 passes; every corpus document has a complete registry entry (SC-008).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T044 [P] Write `README.md` covering the scope statement, architecture overview, setup, the three CLI commands, and a pointer to specs/001-clinical-rag-ingestion/
- [ ] T045 [P] Add `npm run build` static-export configuration and mount the export via FastAPI `StaticFiles` in `backend/app/main.py`, producing the single-process production deployable described in plan.md Structure Decision
- [ ] T046 [P] Add structured logging across `backend/app/ingestion/pipeline.py` and `backend/app/api/search.py` — per-stage timings and counts, so ingest and search performance against SC-001 and SC-007 is observable
- [ ] T047 Perform the manual verification gates from quickstart.md V6 and V7 — read 5 randomly sampled chunks for standalone coherence and trace one chunk back to its stated page in `data/corpus/adrenal-insufficiency-identification-and-management-pdf-66143954919877.pdf`, recording the outcome in `specs/001-clinical-rag-ingestion/quickstart.md` Gate checklist (SC-004, SC-005, Constitution Principle VI)
- [ ] T048 Run the complete quickstart validation suite V1 through V10 and record the outcome of each of the 13 end-of-day review gates in spec.md
- [X] T049 [P] Add a latency check in `backend/tests/integration/test_search_latency.py` timing 10 consecutive searches and asserting each completes under 3 seconds end to end (SC-007)

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
      ↓
Phase 2 Foundational  ← BLOCKS everything below
      ↓
Phase 3 US1 Ingestion (P1) 🎯 MVP
      ↓
Phase 4 US2 Retrieval inspector (P1)   ← needs a populated index
      ↓
Phase 5 US3 Golden evaluation (P2)     ← needs working retrieval
      
Phase 6 US4 Provenance (P3)            ← needs only Phase 2; may run alongside Phase 4/5
      ↓
Phase 7 Polish
```

### User Story Dependencies

- **US1** depends only on Foundational. Fully independent thereafter.
- **US2** depends on US1 — there is nothing to retrieve without an index.
- **US3** depends on US2 — evaluation calls the retriever.
- **US4** depends only on Foundational. Can be built in parallel with US2 and US3 by a second person.

### Within Each User Story

Tests → parsing/transform modules → orchestration → CLI → API → frontend.

### Parallel Opportunities

- **Phase 1**: T002, T003, T004, T007 are independent files.
- **Phase 2**: T008, T011, T013 are independent; T012 needs T011, T014 needs T008.
- **Phase 3**: T016, T017, T018 (three test files) run together. T020 and T021 are independent modules; T022 → T023 → T024 → T025 is a chain.
- **Phase 4**: T031, T032, T033, T034 are four independent frontend files; T029 and T030 are independent of the frontend entirely.
- **Cross-story**: once Phase 2 lands, one person can take US4 (T041–T043) while another drives US1 → US2.

---

## Parallel Example: User Story 1

```bash
# Launch the three transform unit tests together:
T016 backend/tests/unit/test_cleaner.py
T017 backend/tests/unit/test_sectioner.py
T018 backend/tests/unit/test_chunker.py

# Then the two independent transform modules together:
T020 backend/app/ingestion/parser.py
T021 backend/app/ingestion/cleaner.py
```

## Parallel Example: User Story 2

```bash
# Four independent frontend files at once:
T031 frontend/lib/api.ts
T032 frontend/components/ChunkCard.tsx
T033 frontend/components/SearchBox.tsx
T034 frontend/components/IndexStatus.tsx
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

Phases 1 → 2 → 3 deliver a working, fully-attributed vector index driven by one command. That alone satisfies the brief's stated Day 1 requirement: *"A demo-ready knowledge base is not required today. A working first index with visible chunks and metadata is required."*

**Stop and validate here.** Run quickstart V1 and V2, then the manual chunk-quality gates V6 and V7. Constitution Principle V forbids moving on until the foundation holds — and every later quality score is bounded by chunk quality.

### Incremental Delivery

1. **Phases 1–3** → index exists, metadata complete → *Day 1 minimum met*
2. **Phase 4** → question → chunks → page/section in the browser → *demo gate met*
3. **Phase 5** → measurable hit rate → *Day 2 tuning becomes comparable*
4. **Phase 6** → provenance inspectable → *review gates fully evidenced*
5. **Phase 7** → single-process deployable, manual gates recorded

### Parallel Team Strategy

With two developers, after Phase 2:
- **Dev A**: US1 (T016–T025), then US2 backend (T026–T030)
- **Dev B**: US4 (T041–T043), then US2 frontend (T031–T036) against the contract in `contracts/search-api.yaml` — the schema is fixed, so the UI can be built before the endpoint exists

### Scope Discipline

Do not start Phase 5 tuning, hybrid search, reranking, or any generation work until Phase 4's checkpoint passes. `POST /api/generate` returning 501 (T029) is correct behaviour, not an unfinished task — quickstart V9 asserts it.
