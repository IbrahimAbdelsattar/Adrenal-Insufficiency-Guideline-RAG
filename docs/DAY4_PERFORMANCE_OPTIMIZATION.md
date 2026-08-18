# Day 4: Latency Reduction, Token Cost Reduction & Lightweight Graph RAG

**Project:** Clinical Decision Support Lite (Eva AI)  
**Guidelines Ingested:** NICE NG243 (*Adrenal insufficiency: identification and management*)  
**Provider Gateway:** OmniRoute / OpenRouter API (`https://omniroute.dawrly.space/v1`)  
**Focus:** Per-request latency elimination, LLM token cost reduction, SSE streaming, deterministic graph expansion  
**Date:** 2026-08-18  

---

> [!IMPORTANT]
> **Guiding principle:** every optimization must preserve the constitutional
> safety behavior — scope guardrails, abstention, relevance floor, and
> `[Source N]` citation grounding are untouched. Speed and cost work must
> never weaken grounding.

---

## 1. Summary of Results

| # | Optimization | Layer | Measured / Expected Effect |
|---|--------------|-------|---------------------------|
| 1 | Singleton retriever + shared vector store | Backend | Removes per-request Chroma reopen, BM25 rebuild, embedder cache loss (hundreds of ms saved) |
| 2 | Reranker off by default (`hybrid_rerank` → `hybrid`) | Config | Day 2 eval: reranker scored 94.4% hit rate vs 100% for plain hybrid — it added latency *and* reduced quality |
| 3 | `TOP_K` 5 → 3 | Config | ~40% fewer input tokens per generation; k=3 scored the highest precision in the Day 2 eval |
| 4 | Server-side disclaimer | Prompt + API | ~25 output tokens saved per call; model no longer generates boilerplate |
| 5 | LLM response cache (LRU) | Backend | Repeat queries: zero tokens, millisecond responses, `cache_hit` surfaced in API + UI |
| 6 | SSE token streaming (`/api/generate/stream`) | Backend + Frontend | Perceived latency drops to time-to-first-token |
| 7 | Lightweight Graph RAG (deterministic graph + expansion) | Ingestion + Generation | Adjacent clinical context (same section / shared recommendations) added to evidence at zero LLM index cost |

**Verification:** 154/154 backend tests pass, frontend `tsc --noEmit` clean,
live smoke tests on port 8010.

---

## 2. Latency Fixes

### 2.1 Per-request retriever rebuild removed (biggest win)

**Problem.** Every request called `get_retriever(settings)` which constructed:

- a fresh `VectorStore` — reopening the persistent ChromaDB client from disk,
- a fresh `BM25Retriever` — lazily re-reading **all** chunks from Chroma and
  re-tokenizing the entire corpus (`bm25.py::_build_index`),
- a fresh `OpenRouterEmbedder` — whose in-memory query cache was therefore
  discarded on every request, so repeated questions re-paid the embedding
  network hop.

The startup pre-warm in `main.py` built these objects and threw them away.

**Fix.** Process-wide cached singletons in `backend/app/retrieval/factory.py`:

```python
def get_shared_store(settings=None) -> VectorStore: ...      # one Chroma client
def get_shared_retriever(settings=None) -> Retriever: ...    # one retriever
def reset_shared_retriever() -> None: ...                    # after re-ingest
```

Both are double-checked-locked (thread-safe). All request handlers
(`api/generate.py`, `api/search.py`) and the lifespan pre-warm now use them.
The lifespan additionally forces the BM25 index build at startup, so no
request pays that cost.

**Measured:** repeated `/api/search` calls dropped to **7 ms** (cached query
embedding + in-memory index); a novel query costs ~700 ms, dominated by the
embedding network hop to the gateway.

### 2.2 Cross-encoder reranker disabled by default

`RETRIEVER_TYPE` default changed `hybrid_rerank` → `hybrid`
(`backend/app/config.py`). Rationale is our own Day 2 evaluation:

| Pipeline | Hit rate @ k=5 |
|----------|---------------|
| Hybrid + RRF | **100%** |
| Hybrid + RRF + cross-encoder rerank | 94.4% |

The reranker remains available (set `RETRIEVER_TYPE=hybrid_rerank`) and is
still pre-warmed at startup when selected.

### 2.3 SSE token streaming

New endpoint **`POST /api/generate/stream`** (`backend/app/api/generate.py`)
returns `text/event-stream` with three event types:

| Event | Payload | Sent |
|-------|---------|------|
| `meta` | `{query, model, evidence_found, cache_hit}` | once, before generation |
| `token` | `{text}` | per LLM delta (or once for cached/abstained answers) |
| `done` | `{citations, latency_ms, disclaimer}` | once, at completion |
| `error` | `{detail}` | on failure (client shows it verbatim) |

Implementation pieces:

- `LLMClient.stream_completion()` (`generation/client.py`) — async generator
  over the OpenAI-compatible SSE wire format (`data: {...}` / `[DONE]`),
  yielding `choices[0].delta.content`.
- The JSON endpoint `/api/generate` is unchanged and remains the contract for
  programmatic consumers; streaming is additive.
- Abstention paths (out-of-scope / no evidence) short-circuit into a single
  `token` event — the client code path stays uniform.
- Headers `Cache-Control: no-cache` and `X-Accel-Buffering: no` prevent proxy
  buffering.

**Frontend** (`frontend/lib/api.ts`, `frontend/app/page.tsx`):

- `generateStream(query, topK, callbacks)` — fetch + `ReadableStream` SSE
  parser dispatching `onMeta / onToken / onDone / onError`.
- Generate mode now renders the answer **progressively**: the `AnswerCard`
  appears immediately and grows token by token; citations, latency, and
  disclaimer arrive with the `done` event.
- A `streaming` state keeps the SearchBox disabled mid-stream.

### 2.4 Pre-warming

`main.py` lifespan now:

1. Pre-warms the cross-encoder only when `hybrid_rerank` is explicitly set.
2. Builds the shared retriever and eagerly constructs the BM25 index.

---

## 3. Token Cost Reductions

### 3.1 `TOP_K` reduced 5 → 3

`config.py` default and `.env`. Evidence context is 3 chunks × 400–800 tokens
instead of 5 — roughly 40% less input per generation. Justification from the
Day 2 retrieval evaluation: k=3 achieved the highest precision (0.39) with no
hit-rate regression on the golden set.

### 3.2 Disclaimer generated server-side

Previously the system prompt instructed the model to emit a disclaimer
sentence at the end of every answer (~25 output tokens/call, every call).

- `generation/prompt.py` — instruction removed; the prompt now explicitly says
  *“Do not add any disclaimer or closing boilerplate; the application appends
  it.”*
- `generation/citations.py::strip_trailing_disclaimer()` — defensively removes
  a trailing `Disclaimer: …` block if a model still emits one.
- The API already returned a `disclaimer` field; the UI renders it from that
  field, so behavior is unchanged for users.

### 3.3 LLM response cache

`api/generate.py` keeps a process-wide LRU (`RESPONSE_CACHE_SIZE`, default
128) keyed by:

```
top_k | normalized query | '+'-joined retrieved chunk IDs
```

Keying on chunk IDs means the cache is automatically invalidated by a
re-ingest (different chunk IDs) — no manual flush needed.

- Repeat identical query + identical evidence → returns instantly,
  **zero tokens**, `cache_hit: true` in the response.
- `GenerateResponse` gained an additive `cache_hit: bool = False` field;
  `AnswerCard` shows a “cached” badge when set.
- Both JSON and streaming endpoints share the cache; a streamed cache hit is
  emitted as a single `token` event.

### 3.4 Model routing & prompt caching (evaluated, not applied)

- **Model routing** (cheap model for simple lookups): skipped — the OmniRoute
  gateway currently exposes no working chat provider (§6), so routing cannot
  be validated. Revisit once credentials are restored.
- **Prompt caching** (Anthropic cache control): gateway-dependent and
  unverifiable today; the static system prompt is already small.

---

## 4. Lightweight Graph RAG

### 4.1 Why not Microsoft-style GraphRAG

LLM-built entity/community graphs cost many LLM calls at index time and add
multi-hop community-summary lookups at query time — increasing both latency
and token cost, the exact opposite of Day 4 goals. For a **single structured
guideline**, the graph skeleton is already extracted by the ingestion
pipeline (section hierarchy `1.X` / `1.X.X`, numbered recommendation IDs), so
the graph is built **deterministically at zero LLM cost**.

### 4.2 Graph construction (ingestion time)

New module **`backend/app/graph.py`**; integrated at the end of
`ingestion/pipeline.py::run_ingest` (after manifest write).

Edges between chunks:

1. **Section siblings** — chunks whose top-level section matches
   (`1.4.1` and `1.4.2` → both under `1.4`).
2. **Shared recommendations** — chunks citing the same recommendation ID
   (handles cross-references across sections).

Output: `data/index/graph.json` (adjacency map `chunk_id → [chunk_ids]`),
loaded with an mtime-validated module cache (`load_graph`).

**First build result:** 82 nodes, **1,290 undirected edges**, in the same
ingest run (10.5 s total incl. embeddings).

### 4.3 Graph expansion (query time)

In `/api/generate` (and `/api/generate/stream`), after scope classification:

1. `pick_expansion_ids()` walks the top-k results in rank order and selects
   the first unseen linked chunk per seed, up to `GRAPH_MAX_EXPAND`
   (default **1**) extra chunks.
2. Chunks are fetched by ID via the new `VectorStore.get_chunks(ids)`.
3. `wrap_expanded()` appends them as `RetrievalResult`s ranked after the
   seeds (`retriever_mode="graph"`, `below_floor=False`), so they become an
   extra `[Source N]` evidence block the model may cite.

Settings:

| Env var | Default | Meaning |
|---------|---------|---------|
| `GRAPH_EXPANSION` | `true` | Master switch |
| `GRAPH_MAX_EXPAND` | `1` | Max extra evidence chunks per query |

The cap of 1 keeps the token budget bounded (one extra evidence block ≈
200–800 tokens) while giving the generator adjacent context — e.g. adrenal
crisis dosing next to sick-day rules.

---

## 5. Files Changed

| File | Change |
|------|--------|
| `backend/app/config.py` | `TOP_K` 5→3, `RETRIEVER_TYPE` default `hybrid`, new `GRAPH_EXPANSION` / `GRAPH_MAX_EXPAND` / `RESPONSE_CACHE_SIZE` settings |
| `.env` | Mirrors new defaults |
| `backend/app/retrieval/factory.py` | `get_shared_store` / `get_shared_retriever` / `reset_shared_retriever` singletons |
| `backend/app/api/generate.py` | Rewritten: shared retriever, graph expansion, response cache, disclaimer stripping, new `/api/generate/stream` SSE endpoint |
| `backend/app/api/search.py` | Shared store + shared retriever (no per-request rebuild) |
| `backend/app/main.py` | Lifespan pre-warms the shared retriever and builds the BM25 index |
| `backend/app/retrieval/store.py` | `get_chunks(ids)` fetch-by-ID for graph expansion |
| `backend/app/generation/client.py` | Refactored helpers + `stream_completion()` async generator |
| `backend/app/generation/prompt.py` | Disclaimer instruction removed from system prompt |
| `backend/app/generation/citations.py` | `strip_trailing_disclaimer()` |
| `backend/app/models.py` | `GenerateResponse.cache_hit` (additive) |
| `backend/app/graph.py` | **New** — deterministic graph build/save/load/expansion |
| `backend/app/ingestion/pipeline.py` | Builds + saves `graph.json` at end of ingest |
| `frontend/lib/api.ts` | `generateStream()` SSE client, stream types, `cache_hit` field |
| `frontend/app/page.tsx` | Progressive rendering of streamed answers, `streaming` state |
| `frontend/components/AnswerCard.tsx` | “cached” badge |

### Tests

| File | Change |
|------|--------|
| `backend/tests/unit/test_graph.py` | **New** — 9 tests: edge rules, expansion picking/dedup, wrapping, disclaimer stripping |
| `backend/tests/unit/test_config.py` | Updated for new `hybrid` default |
| `backend/tests/integration/test_generate_api.py` | Mock target renamed; +3 tests: response cache avoids second LLM call, SSE meta/token/done sequence, streamed cache hit |

**Suite status:** 154 passed (142 pre-existing + 12 new).

---

## 6. Known Issue: OmniRoute Chat Credentials Down

During end-to-end verification the gateway rejected **all** chat providers:

| Provider probe | Response |
|----------------|----------|
| `anthropic/*` | `No active credentials for provider: anthropic` |
| `google/*`, `openai/*` | `No active credentials for provider: <provider>` |
| `deepseek/deepseek-chat` | `403: You have no permission to access this resource` |

Embeddings still work (`gemini/gemini-embedding-001` ingest succeeded).
Everything up to the LLM call is verified live (retrieval 7 ms cached,
SSE `meta` event emitted, graceful `error` event on LLM failure). **Action
required:** restore gateway chat credentials, or set `GENERATION_MODEL` /
`OMNIROUTE_BASE_URL` to a working provider.

---

## 7. Configuration Reference (new/changed)

```dotenv
TOP_K=3                 # evidence chunks per query (was 5)
RETRIEVER_TYPE=hybrid   # default; hybrid_rerank still available
GRAPH_EXPANSION=true    # enable graph-linked evidence expansion
GRAPH_MAX_EXPAND=1      # max extra chunks added from the graph
RESPONSE_CACHE_SIZE=128 # LRU entries for repeat queries
```

---

## 8. Follow-up Opportunities

1. **Model routing** — cheap fast model for simple factual lookups, Sonnet for
   synthesis (blocked on gateway credentials, §6).
2. **Anthropic prompt caching** — static system prompt is cache-friendly once
   the provider is reachable.
3. **Query-side graph use** — currently only evidence expansion; a future step
   could route multi-hop questions (“management during surgery”) through
   recommendation-link traversal before retrieval.
4. **Re-evaluate the reranker** with a stronger cross-encoder (e.g. a
   clinical/biomedical variant) before deciding to keep it disabled.
