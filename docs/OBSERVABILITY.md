# Backend Observability — RAG & LLM Logging

Every request through the RAG pipeline is timed stage by stage and summarised
in a single log line. This document is the map: what is logged, where it comes
from, and how to answer "why was that answer slow?" without re-running it.

Error reporting to Sentry is documented separately in [ERROR_TRACKING.md](./ERROR_TRACKING.md);
the two share the `backend/app/monitoring/` package and the same span names.

---

## 1. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` adds per-chunk scores, BM25 term matches, embedding cache hits |
| `LOG_FORMAT` | `text` | `text` for humans, `json` for log aggregators |
| `LOG_QUERY_TEXT` | `true` | `false` replaces query text with `<redacted len=N>` |
| `LOG_QUERY_MAX_CHARS` | `200` | Truncation limit for logged query text |
| `SLOW_REQUEST_MS` | `5000` | At or above this, the request line is `WARNING` and tagged `[SLOW]` |
| `LOG_PROMPT_PREVIEW` | `false` | `DEBUG`-level prompt and answer previews |
| `LOG_PREVIEW_CHARS` | `400` | Preview truncation limit |

**PHI safety.** Query text is scrubbed through the same `scrub_text()` used for
Sentry events — emails, phone numbers, SSNs, MRNs, and bearer tokens are
replaced before anything reaches a log line — then truncated. Chunk *ids* are
logged; chunk *text* is not, except under `LOG_PROMPT_PREVIEW=true`.

---

## 2. Correlation ids

`request_logging_middleware` (in `backend/app/main.py`) assigns a 12-hex-char
id to every request and binds it to a `ContextVar`. Every log line emitted
while handling that request carries it in the `request_id` field:

```
10:57:12 INFO  [a0a58035e0f4] backend.app.rag: rag.stage retrieval ok in 1029.9 ms | ...
```

- An inbound `X-Request-ID` header is honoured, so a trace can span frontend
  and backend.
- The id is echoed back as `X-Request-ID`, alongside `X-Response-Time-ms`.
- Outside a request (startup, CLI, pre-warm) the field is `-`.

To reconstruct one call: `grep a0a58035e0f4 backend.log`.

---

## 3. The `rag.trace` summary line

One line per `/api/search`, `/api/generate`, and `/api/generate/stream` call,
with the full stage breakdown:

```
rag.trace generate status=ok total=46189ms
  stages={'guardrail': 0.11, 'retrieval': 24918.68, 'scope': 0.05,
          'graph_expansion': 3.78, 'cache_lookup': 0.07, 'prompt_build': 0.08,
          'llm': 21264.66, 'citations': 0.71}
  query="What is the hydrocortisone dose in adrenal crisis?" results=3 above_floor=3
  top_relevance=0.794 retriever_mode=hybrid scope_status=in_scope graph_expanded=1
  evidence_chunks=4 cache_hit=false sources=4 evidence_chars=13450 model=eva-ai
  llm_ms=21262.74 finish_reason=stop answer_chars=1411 citations=3
  prompt_tokens=3325 completion_tokens=370 total_tokens=5294
```

### Stages

| Stage | Endpoint | Covers |
|---|---|---|
| `guardrail` | generate | Prompt-injection detection |
| `retrieval` | all | Hybrid search: embed → dense → BM25 → fusion → rerank |
| `scope` | all | in_scope / no_evidence / out_of_scope classification |
| `graph_expansion` | generate | Graph-linked extra evidence chunks |
| `cache_lookup` | generate | LRU response-cache probe |
| `prompt_build` | generate | Evidence assembly and prompt construction |
| `llm` | generate | OmniRoute completion (or the full stream) |
| `citations` | generate | `[Source N]` resolution against the cited sources |

`overhead_ms` is total minus the sum of the stages — serialization and
framework cost. A large value means something outside the instrumented stages
is expensive.

### Statuses

`ok`, `ok_cached`, `abstained_out_of_scope`, `abstained_no_evidence`,
`refused_injection`, `error_reasoning_only`, `error`.

---

## 4. What each layer logs

### Retrieval

| Event | Level | Key fields |
|---|---|---|
| `embedding.query` | INFO | `cache_hit`, `model`, `dimensions`, `duration_ms` |
| `embedding.retry` / `embedding.exhausted` | WARNING / ERROR | `attempt`, `error` |
| `retrieval.dense.embed` / `.query` | DEBUG | `dims`, `hits`, `top_score` |
| `retrieval.bm25.index` | INFO | `chunks`, `vocabulary`, `avg_doc_len`, `duration_ms` |
| `retrieval.bm25` | DEBUG | `query_terms`, `matched_terms`, `max_raw_score` |
| `retrieval.hybrid.fusion` | DEBUG | `dense_hits`, `bm25_hits`, `overlap`, `fused_candidates` |
| `retrieval.rerank` | DEBUG | `candidates`, `top_score`, `reordered` |
| `rerank.fallback` | WARNING | Cross-encoder unavailable — ordering is fusion order |
| `retrieval.hybrid` | INFO | `results`, `above_floor`, `top_relevance`, `chunk_ids` |

Two fields are worth watching specifically:

- **`overlap`** — how many chunks dense and BM25 both returned. Near zero means
  the lexical and semantic sides disagree entirely.
- **`matched_terms=0`** — the query shares no vocabulary with the corpus, a
  strong out-of-scope signal independent of the cosine score.

### LLM (OmniRoute)

| Event | Level | Key fields |
|---|---|---|
| `llm.request` | INFO | `model`, `prompt_chars`, `est_prompt_tokens`, `max_tokens`, `temperature` |
| `llm.response` | INFO / ERROR | `duration_ms`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `tokens_per_second`, `finish_reason`, `attempt` |
| `llm.retry` | WARNING | `status_code`, `attempt`, `retry_in_s` |
| `llm.truncated` | WARNING | `finish_reason=length` — the answer is cut off at `max_tokens` |
| `llm.ttft` | INFO | `ttft_ms` — time to first streamed token |
| `llm.stream` | INFO | `ttft_ms`, `stream_ms`, `deltas`, `answer_chars`, `finish_reason` |
| `stream.first_visible_token` | INFO | First token after reasoning filtering — what the user sees |

Token counts come from the gateway's `usage` block when present; `est_*`
fields are a ~4-chars-per-token estimate for prompt sizing only.

### Guardrails and grounding

| Event | Level | Meaning |
|---|---|---|
| `guardrail.injection` | WARNING | Prompt injection detected; generation refused |
| `citations.empty` | WARNING | Answer resolved zero citations despite supplied evidence — possible ungrounded answer |
| `graph.expansion` | INFO | `added`, `added_chunk_ids` |
| `cache.hit` / `cache.evict` | INFO / DEBUG | Response-cache behaviour |

---

## 5. `GET /api/metrics`

Live latency read-out for the current worker process:

```json
{
  "status": "ok",
  "config": { "retriever_type": "hybrid", "generation_model": "eva-ai", "top_k": 3 },
  "window": 512,
  "counters": {
    "generate.cache.hit": 1,
    "generate.scope.in_scope": 2,
    "generate.status.ok": 1,
    "llm.calls": 1,
    "llm.total_tokens": 5294
  },
  "stages": {
    "generate.llm":       { "count": 1, "avg_ms": 21264.66, "p50_ms": 21264.66, "p95_ms": 21264.66, "max_ms": 21264.66 },
    "generate.retrieval": { "count": 3, "avg_ms": 16237.49, "p50_ms": 23781.68, "p95_ms": 24918.68, "max_ms": 24918.68 },
    "retrieval.dense.embed": { "count": 3, "avg_ms": 16224.40, "p50_ms": 23773.85, "p95_ms": 24899.27, "max_ms": 24899.27 }
  }
}
```

Rolling window of the last 512 observations per stage, in memory, per process.
It resets on restart and is not shared between workers — a tuning read-out,
not a metrics backend. For durable metrics, ship the JSON logs.

The same snapshot is written to the log at shutdown (`event=shutdown`).

---

## 6. Recipes

**Where did the time go on one request?**
```bash
grep "$REQUEST_ID" backend.log
```

**Which stage dominates overall?**
```bash
curl -s localhost:8000/api/metrics | jq '.stages | to_entries | sort_by(-.value.p95_ms) | .[:5]'
```

**Every slow request:**
```bash
grep '\[SLOW\]' backend.log
```

**Token spend per query (JSON logs):**
```bash
jq -r 'select(.event=="rag.trace") | [.query, .total_tokens, .total_ms] | @tsv' backend.log
```

**Answers that cited nothing:**
```bash
jq 'select(.event=="citations.empty")' backend.log
```

**Cache effectiveness:**
```bash
curl -s localhost:8000/api/metrics | jq '.counters | with_entries(select(.key|startswith("generate.cache")))'
```

---

## 7. Adding instrumentation

For a stage inside a request, use the request's `RagTrace`:

```python
with trace.stage("my_stage", extra_field="value") as span:
    result = do_work()
    span["items"] = len(result)
```

For code not tied to a request (retrieval internals, ingestion):

```python
from backend.app.monitoring import stage_timer

with stage_timer("retrieval.my_step", logger, top_k=k) as span:
    span["hits"] = len(hits)
```

Both log a line, record into `REGISTRY` for `/api/metrics`, open a matching
Sentry span, and mark the stage failed (without swallowing the exception) if
the block raises.
