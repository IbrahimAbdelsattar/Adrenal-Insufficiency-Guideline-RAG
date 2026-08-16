# Phase 0 — Research & Decisions

**Feature**: 001-clinical-rag-ingestion | **Date**: 2026-08-16

All Technical Context unknowns are resolved. No `NEEDS CLARIFICATION` markers remain.

---

## D1 — Application topology

**Decision**: Monolithic repository, two processes in development (FastAPI `:8000`,
Next.js `:3000` with a `/api/*` rewrite). Production builds the frontend to a static
export served by FastAPI `StaticFiles` as a single deployable.

**Rationale**: Lowest operational overhead for a one-day build. The dev rewrite removes
CORS from the critical path while keeping hot reload on both sides. Collapsing to one
process for deployment means no orchestration, no reverse proxy, no second host.

**Alternatives considered**:
- *Next.js BFF proxying to FastAPI* — buys server-side key hiding and server components,
  costs an extra network hop and more moving parts. No auth exists yet, so the benefit is
  unrealised.
- *Docker Compose, separate services* — better for team parallelism, but a container
  dependency and setup time the hackathon cannot spare.
- *FastAPI-only with a static SPA* — essentially the chosen production mode, but adopting
  it in development would forfeit Next's dev server ergonomics.

---

## D2 — Vector store

**Decision**: ChromaDB, embedded persistent client, writing to `data/index/`.

**Rationale**: `pip install` and nothing else — no server, no Docker, no migrations.
Critically, Chroma stores arbitrary metadata **on the vector entry** and returns
documents, metadata, and distances from a single `query()` call. That satisfies
Constitution Principle II structurally rather than by convention.

**Alternatives considered**:
- *Qdrant* — superior filtering and native hybrid search, genuinely better for Day 2, but
  needs Docker. Revisit when hybrid retrieval is actually built.
- *Supabase pgvector* — persistent and team-shareable, but requires network, migrations,
  and RPC functions for similarity search.
- *FAISS + JSON sidecar* — **rejected on principle**. Metadata living outside the index
  is exactly the drift failure Principle II forbids.

**Note**: Chroma metadata values must be scalars (str/int/float/bool). No nested objects
— the data model flattens accordingly.

---

## D3 — Model provider and embedding model

**Decision**: OpenRouter as the sole provider. Embeddings via
`openai/text-embedding-3-small` (1536-dim) against the OpenAI-compatible
`POST https://openrouter.ai/api/v1/embeddings` endpoint.

**Rationale**: One API key covers embeddings today and generation on Day 2, with the
model selectable by config string. `text-embedding-3-small` is cheap (~$0.02/M tokens),
fast, and the most documented option if something breaks mid-hackathon.

**Verification performed**: OpenRouter historically exposed only chat completions, so
embeddings support was confirmed before committing to this design. As of August 2026
OpenRouter serves a dedicated OpenAI-compatible embeddings endpoint alongside
`/images`, `/videos`, and `/audio/*`. Streaming is not supported for embeddings, which is
irrelevant here.

**Alternatives considered**:
- *`qwen/qwen3-embedding-8b`* — stronger retrieval benchmarks, but 4096-dim vectors mean
  slower indexing and more storage.
- *`cohere/embed-v3`* — its `search_document` / `search_query` input modes genuinely help
  asymmetric retrieval. Worth revisiting on Day 2 if hit rate disappoints.
- *Local `bge-small-en-v1.5`* — free and offline, but a model download and slow CPU
  embedding for no quality gain at this corpus size.

**Implementation notes**: batch inputs, retry on 429/5xx with exponential backoff, and
persist the model id into the index manifest so an index built with one model is never
queried with another.

### D3a — Revised in implementation: OmniRoute, not OpenRouter

"Omniroute" turned out to be **OmniRoute**, a self-hostable multi-provider AI gateway —
not OpenRouter. The two were conflated during planning. Corrected against the running
instance:

| | Planned | Actual |
|---|---|---|
| Base URL | `https://openrouter.ai/api/v1` | `https://omniroute.dawrly.space/v1` |
| Embedding model | `openai/text-embedding-3-small` | `gemini/gemini-embedding-001` |
| Dimensions | 1536 | 3072 |

OmniRoute is OpenAI-compatible, so `OpenRouterEmbedder` worked unchanged once the base
URL was corrected — the provider seam did its job.

The model changed because the gateway's OpenAI-backed routes have no upstream credential
configured: `openai/*` returns *"No credentials for embedding provider"*, and
`openrouter/*` returns 401 *"User not found"*. Of the 33 embedding models the gateway
lists, `gemini/gemini-embedding-001` was the one that authenticated and returned vectors.
Batch size was lowered from 100 to 32 for the Gemini route.

**Verified**: 95 chunks embedded and indexed in 34 s; a live query returns §1.7
"Emergency management of adrenal crisis" (p.27) at score 0.808 for *"How should an
adrenal crisis be managed?"*.

**Follow-up**: the class name `OpenRouterEmbedder` and the `OPENROUTER_*` env vars are
now misnomers. Renaming to `GatewayEmbedder` / `GATEWAY_*` is cosmetic and deferred —
it would touch config, .env, and docs for no functional gain during the hackathon.

---

## D4 — PDF parsing

**Decision**: PyMuPDF (`fitz`), extracting with `page.get_text("dict")` to retain
font size, weight, and bounding boxes per span.

**Rationale**: Fast, reliable page numbering, and the span-level font metadata is what
makes heading detection possible without an ML layout model. Single dependency, no
model downloads.

**Alternatives considered**:
- *pdfplumber* — better table extraction, materially slower, weaker heading signal.
  Already installed in this environment; kept as a fallback if NG243 dosing tables prove
  unreadable.
- *Docling* — highest structural fidelity, but a heavy dependency with a slow first run.
  Disproportionate for a single well-structured PDF.

**Licensing note**: PyMuPDF is AGPL-3.0. Acceptable for a hackathon; flagged should this
project ever be distributed commercially.

---

## D5 — Cleaning strategy

**Decision**: Frequency-based boilerplate removal plus targeted glyph repair.

**Rationale**: Grounded in direct inspection of NG243 rather than assumption. Observed
artefacts:

| Artefact | Observed | Treatment |
|---|---|---|
| Running footer `Adrenal insufficiency: identification and management (NG243)` | Every content page | Frequency detection: a line appearing on >60% of pages is boilerplate |
| Rights notice `© NICE 2026. All rights reserved…` | Every page | Same frequency rule |
| Bullet glyph extracted as `�` | Throughout recommendation lists | Normalise to `- ` |
| Contents page with dot leaders (`......... 5`) | Page 3 | Regex `\.{4,}\s*\d+\s*$` marks the page as front matter |
| Front matter — cover, "Your responsibility", contents | Pages 1–5 | Skipped: no numbered recommendation present |
| Hyphenated line-break splits | Occasional | Rejoin `(\w+)-\n(\w+)` when the result is a known word form |

Frequency detection is used in preference to hard-coded strings so a second source
document does not require new code.

---

## D6 — Chunking strategy

**Decision**: NICE-structure-aware chunking with token packing. Detect the `N.N` section
and `N.N.N` recommendation hierarchy; treat each numbered recommendation as **atomic**;
pack consecutive siblings within the same section up to a ~600-token target (400 floor,
800 ceiling) without ever splitting a recommendation.

**Rationale**: Confirmed directly against NG243's structure — `1.1 Information, support
and decision making` → `1.1.1`, `1.1.2`, with prose sub-headings like *"When to suspect
adrenal insufficiency"* nested between. A numbered recommendation is precisely the
"one coherent clinical idea" the brief demands, and it is exactly the unit a clinician
would cite. Splitting one mid-sentence would produce a chunk that is both incoherent and
dangerously partial.

Oversized single recommendations are emitted whole and flagged, never truncated — a
truncated clinical recommendation can invert its own meaning.

**Alternatives considered**:
- *Recursive character splitter* — 5 minutes to write, but cuts blindly through
  recommendations and reduces `section_title` to guesswork.
- *Docling heading tree* — better structure with no regex tuning, at the cost of a heavy
  dependency.
- *Semantic breakpoint chunking* — an extra embedding pass, unpredictable on clinical
  prose, and destroys clean page and section boundaries.

**Token counting**: `tiktoken` with `cl100k_base`, matching the embedding model's family.

### D6a — Observed outcome: the 400-token floor is a target, not a constraint

Measured on the real NG243 ingest: 95 chunks, mean 190 tokens, median 93. Only 15 land
inside the nominal 400–800 band.

This was investigated rather than tuned away. The short chunks are overwhelmingly
**correct**: §1.9 "Terms used in this guideline" is a glossary whose entries are
self-contained definitions ("Physiological stress" at 36 tokens, "Sick-day dosing" at
39). Each is exactly the "one coherent clinical idea" FR-013 asks for.

Two options were weighed for raising the mean:

1. *Pack across sub-section boundaries within a section.* *Rejected — clinical safety.*
   NG243 splits several sections into "People aged 16 and over" and "Children and young
   people". Merging those would place adult and paediatric dosing in one chunk, and a
   retrieval hit would then present both as equally applicable. That is a far worse
   failure than a short chunk.
2. *Merge adjacent short blocks regardless of heading.* Rejected — it would fuse
   unrelated glossary terms and dilute their embeddings.

**Decision**: the sub-section boundary stays hard. `CHUNK_TARGET_TOKENS` governs packing
*within* a boundary; it never overrides one. FR-012's band is therefore satisfied as a
packing target, and the measured distribution is a property of the source document, not
a defect. Retrieval quality is measured directly by the golden set (D9), which is the
metric that actually matters.

---

## D7 — Retrieval strategy

**Decision**: Dense cosine top-K only, behind a `Retriever` protocol.

**Rationale**: The brief explicitly forbids optimisation before a baseline retrieves
reasonable evidence, and Constitution Principle V codifies that. The protocol costs
roughly ten lines and lets Day 2 substitute hybrid or reranked retrieval without the API
layer noticing.

Results below the relevance floor are returned **flagged, not filtered** — Principle VI
requires weak results to stay observable.

**Deferred to Day 2**: BM25 + dense with reciprocal rank fusion (clinical queries carry
exact drug and dose terms that dense vectors blur); cross-encoder reranking (retrieve 30,
rerank to 5 — typically the single largest quality gain).

---

## D8 — Corpus and provenance

**Decision**: Filesystem corpus at `data/corpus/` with a `data/sources.yaml` registry.
Ingestion **fails** on any PDF lacking a registry entry.

**Rationale**: Reproducible and reviewable in git. Fail-closed registration is what makes
Principle III enforceable rather than aspirational — an undocumented source cannot
silently enter the index.

**Corpus**: NICE NG243 only. The WHO Drug Information 2003 bulletin was evaluated and
excluded: it is a periodical rather than a guideline, 23 years old, and spans unrelated
topics. It fails Principle III on three counts.

**Alternatives considered**:
- *Upload endpoint* — a better demo moment, but needs background jobs, progress state,
  and error handling. Specified in `contracts/` as future work.

---

## D9 — Evaluation

**Decision**: `golden_questions.yaml` holding ≥10 clinical questions, each with an
expected source section, executed by a pytest suite asserting top-K containment and
reporting an aggregate hit rate.

**Rationale**: Turns the brief's "run 5–10 clinical questions" gate into a regression
test. Without it, tomorrow's chunking changes are unmeasurable — the hit rate is the only
evidence that a tuning change helped rather than hurt.

**Target**: ≥8/10 questions retrieve their expected section within top-5 (SC-003).

**Alternatives considered**:
- *Manual inspection only* — faster to set up, no regression safety.
- *Full Recall@k / MRR / nDCG harness* — real labelling effort, over-engineered for a
  single-document corpus.

---

## D10 — Configuration and secrets

**Decision**: `pydantic-settings` reading `.env`. All tunables — embedding model, chunk
target/floor/ceiling, top-K, relevance floor, paths — are settings fields. `.env.example`
is committed; `.env` is not.

**Rationale**: Constitution Operating Constraints forbid magic numbers scattered through
modules. Day 2 tuning should mean editing one file, and every eval run should be able to
record the exact configuration that produced it.

---

## Resolved Unknowns Summary

| Unknown | Resolution |
|---|---|
| Language/Version | Python 3.13, TypeScript 5.x / Node 24 (both verified present) |
| Primary Dependencies | FastAPI, PyMuPDF, ChromaDB, tiktoken, httpx, pydantic v2 / Next.js 15, React 19, Tailwind |
| Storage | ChromaDB embedded at `data/index/`; PDFs and YAML on filesystem |
| Testing | pytest — unit, integration, golden-set eval |
| Target Platform | Local dev, single-host deployment |
| Project Type | Monolithic web application |
| Performance Goals | Ingest <10 min; search <3 s |
| Constraints | One provider, no GPU, no Docker, no auth, index persists |
| Scale/Scope | 1 document, 63 pages, ~150–350 chunks, single user |
