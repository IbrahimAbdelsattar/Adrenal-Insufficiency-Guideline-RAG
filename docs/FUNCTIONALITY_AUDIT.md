# Functionality Audit — Eva AI Clinical Decision Support

**Date:** 2026-08-18
**Scope:** Verify every endpoint and CLI command works end-to-end against the real
index and a live LLM; confirm no sample, mock, or placeholder data reaches the user;
document all findings and changes.

Verification was done by running the system, not by reading code alone. Every claim
below is backed by an observed run.

---

## 1. Summary

Eight defects were found. Seven are fixed and verified; one is a configuration issue
you should be aware of. Four of the defects broke a stated requirement outright:

| # | Defect | Severity | Status |
|---|--------|----------|--------|
| 1 | `/api/generate` returned 503 on every request | Blocker | Fixed |
| 2 | Configured LLM had no credentials on the gateway | Blocker | Fixed (model changed) |
| 3 | Citations silently dropped when the model wrote `[Source 3, 1.7.1]` | Blocker | Fixed |
| 4 | Citations empty when the model cited `[1.8.6]` instead of `[Source N]` | Blocker | Fixed |
| 5 | Out-of-scope guardrail never fired — any question was answered | Critical | Fixed |
| 6 | Latent citation misnumbering between prompt and response | High | Fixed |
| 7 | Stale eval test asserted nothing (patched a function that no longer exists) | Medium | Fixed |
| 8 | UI claimed "1536-dim OpenRouter embeddings"; index is 3072-dim Gemini | Low | Fixed |

**Test suite: 173 passed** (was 162 passed / 1 failed). `ruff` clean. Frontend
typecheck and production build clean.

---

## 2. Sample / placeholder data check

**Result: no sample data reaches the user.** Everything served is derived from one
real registered PDF.

| Checked | Finding |
|---|---|
| `backend/app/**` | No mock/dummy/placeholder/TODO/hardcoded fixtures. The only match for "placeholder" is `_reject_placeholder`, a validator that *rejects* placeholder text. |
| `frontend/**` | Only matches are the `placeholder` attribute on the search input. |
| `data/corpus/` | One real PDF: NICE NG243 (`adrenal-insufficiency-...pdf`). |
| `data/sources.yaml` | One registered source with real publisher, year, URL, licence and credibility notes. Ingestion fails closed on unregistered files. |
| `data/index/manifest.json` | Real build: 1 document, 82 chunks, 63 pages processed, `gemini/gemini-embedding-001`, 3072 dims. |
| Chunk metadata (all 82) | `missing_page=0 missing_section=0 missing_doc=0`. |
| Mock objects in tests | Confined to `backend/tests/`, as intended. |

One piece of **inaccurate UI copy** was found and fixed — see defect 8.

---

## 3. Defects found and fixed

### 3.1 `/api/generate` returned 503 on every request — `backend/app/generation/client.py`

The OmniRoute gateway defaults to an SSE response when the request body omits
`stream`. The non-streaming client called `response.json()` on `data: {...}` frames
and raised `Expecting value: line 1 column 1 (char 0)`, surfaced as a 503.

The streaming endpoint worked; the JSON endpoint never did.

```python
"temperature": self._settings.generation_temperature,
# Explicit: some OmniRoute routes default to SSE when `stream` is absent,
# which breaks the non-streaming JSON parse in generate_completion().
"stream": False,
```

Confirmed against the gateway: with `"stream": false` the same model returns a
normal `chat.completion` object.

### 3.2 Configured model had no credentials — `.env`, `.env.example`

`GENERATION_MODEL=anthropic/claude-sonnet-4.5` returned:

```
404 {"error":{"message":"No active credentials for provider: anthropic", ...}}
```

Probing the gateway's 3741 advertised models with your key:

| Route | Result |
|---|---|
| `anthropic/claude-sonnet-4.5` | 404 no active credentials |
| `kc/anthropic/claude-sonnet-4.6` | 402 add credits |
| `kc/google/gemini-3-flash-preview` | 401 sign in required |
| `kilocode/openai/gpt-5.4-mini` | 401 sign in required |
| `google/gemini-3-flash` | 403 credit card required |
| `auto/chat` | **works** (routes to gemini-3.1-flash-lite / llama-3.1-8b) |

`GENERATION_MODEL=auto/chat` is now set in `.env` and `.env.example`. **This is the
one change you may want to revisit** — `auto/*` is a router, so the underlying model
varies per request. If you want a fixed clinical-grade model, the gateway needs
upstream credentials for it; that is an account action, not a code change.

### 3.3 Citations dropped on `[Source 3, 1.7.1]` — `backend/app/generation/citations.py`

The extractor required a `]` immediately after the digits:

```python
re.findall(r"\[Source (\d+)\]", text)   # before
```

Models routinely append the NICE recommendation id inside the bracket. On a real
query the answer was fully grounded and cited `[Source 3, 1.7.1]` throughout — and
the API returned `citations: []`. Now:

```python
re.findall(r"\[Source\s*(\d+)[^\]]*\]", text)
```

### 3.4 Citations empty when the model cited `[1.8.6]` — `citations.py`, `prompt.py`

Worse than 3.3: on "What monitoring is needed during glucocorticoid replacement?" the
model cited NICE recommendation numbers (`[1.8.6]`, `[1.8.7]`) and never wrote
`[Source N]` at all. Result: a 2183-character grounded answer with **zero** citations.

Citation completeness cannot depend on the model formatting its markers correctly.
Two changes:

**A stricter prompt** (`prompt.py`) that names `[Source N]` as the only accepted
format, offers `[Source 2, 1.8.6]` for combining both, and explicitly forbids bare
recommendation numbers.

**A layered resolver** (`resolve_citations`) as a structural guarantee:

1. `source_marker` — explicit `[Source N]` markers (claim-level).
2. `recommendation_id` — bare `[1.8.6]` markers mapped back to the chunk whose
   indexed `recommendation_ids` contain them (still exact — 34 of 82 chunks carry them).
3. `fallback_all_sources` — no markers found, so every chunk the model was shown is
   listed (block-level provenance).

Each citation now carries `resolved_by` so the attribution level is auditable rather
than implied. **Layer 3 fired on a real run** ("How should glucocorticoid withdrawal
be tapered?"), which is exactly the case that previously shipped with no citations.

### 3.5 Out-of-scope guardrail never fired — `hybrid.py`, `scope.py`, `models.py`, `config.py`

**The most serious finding.** The system answered *any* question from the NICE
guideline, including "how do I bake sourdough bread at home", which classified as
`in_scope` with a top score of exactly `1.000`.

Root cause: `HybridRetriever` fuses ranks with RRF, then normalises by the top hit:

```python
ranked_pairs = [(chunks_map[cid], s / max_rrf) for cid, s in fused_sorted[:k]]
```

RRF scores are rank-based and carry no absolute relevance information, and dividing
by the maximum makes rank 1 exactly `1.0` for every query. Both guardrails compared
against that value, so `below_floor` was never `True` and `scope_threshold` was
unreachable. The config comment even noted the threshold was "tuned against the
cross-encoder reranker scale" — but the reranker is disabled by default, so that
scale was never in use.

Fix — judge guardrails on an absolute signal:

```python
# models.py
@property
def absolute_relevance(self) -> float:
    """Scale-stable relevance signal for floor / scope decisions."""
    if self.rerank_score is not None:
        return self.rerank_score
    if self.dense_score is not None:
        return self.dense_score
    return self.score
```

`score` still orders results; `absolute_relevance` decides floor and scope.

Thresholds retuned against measured cosine values (8 in-scope vs 8 unrelated queries):

| | min | max |
|---|---|---|
| In-scope top relevance | 0.700 | 0.810 |
| Unrelated top relevance | 0.462 | 0.526 |

A clean gap of 0.174. Set `SCOPE_THRESHOLD=0.58`, `RELEVANCE_FLOOR=0.62`.

Verified live — all four now abstain, and clinical queries are unaffected:

```
in_scope      evidence=True  n=3  | How should an adrenal crisis be managed in adults?
out_of_scope  evidence=False n=0  | how do I bake sourdough bread at home
out_of_scope  evidence=False n=0  | what is the capital of Japan
out_of_scope  evidence=False n=0  | treatment of type 2 diabetes with metformin
```

The last one matters: a genuine clinical question that is outside the *registered
corpus* is now refused rather than answered from unrelated adrenal guidance.

Retrieval quality did not regress: `cli eval` still reports **100% hit rate (18/18)**,
mean rank 1.83, P@3 0.39.

### 3.6 Latent citation misnumbering — `assembler.py`, `api/generate.py`

`assemble_evidence` dropped `below_floor` chunks and renumbered the remaining blocks
`[Source 1..N]`, while `extract_citations` indexed into the **unfiltered** list. Any
dropped chunk shifted every subsequent citation onto the wrong page.

This could not trigger while defect 3.5 was live (nothing was ever `below_floor`), so
fixing 3.5 would have activated it. Both were fixed together.

The selection is now a single shared function, and the call sites pass the same list
to both consumers:

```python
cited_sources = select_sources(evidence_results)
evidence_text  = assemble_evidence(evidence_results)
...
citations = resolve_citations(answer, cited_sources)
```

### 3.7 Eval test asserted nothing — `backend/tests/eval/test_generation_quality.py`

The test monkeypatched `generate_module.get_retriever`, removed in the shared-retriever
refactor, and died with `AttributeError` before reaching any assertion. Retargeted to
`get_shared_retriever`.

### 3.8 Inaccurate UI copy — `frontend/lib/translations.ts`

The empty state claimed *"Powered by 1536-dim OpenRouter embeddings"*. The index is
3072-dim `gemini/gemini-embedding-001`. Replaced (EN and AR) with a description of the
actual hybrid dense + BM25 retrieval that points at the sidebar, which already reads
the real model and dimensions live from `/api/index`.

### 3.9 Duplicated section number in citations — `frontend/components/AnswerCard.tsx`

The UI rendered **"1.7 1.7 Emergency management of adrenal crisis"**. The sectioner
stores `section_title` with its number already prefixed, so joining number + title
doubled it. Added a `formatSection` helper that skips the prefix when the title
already starts with it.

### 3.10 CLI bypassed the scope guardrail — `backend/app/cli.py`

`cli query` displayed `result.score` (always `1.000`, per 3.5) as if it were relevance,
and its human-readable path never called `classify_scope` — so it would print evidence
for questions the API refuses. It now applies the same guardrail and prints the
absolute signal:

```
Retriever: hybrid | Model: gemini/gemini-embedding-001 | top_k=3 | floor=0.62 | scope=0.58
#1  rel=0.773  NICE NG243 ...  p.28  sec 1.7 - 1.7 Emergency management of adrenal cr
```

```
Query: how do I bake sourdough bread
scope: out_of_scope
This question is outside the current scope of Eva AI. ...
```

---

## 4. Verification performed

All runs used the real ChromaDB index (82 chunks) and live LLM calls.

### API endpoints

| Endpoint | Result |
|---|---|
| `GET /api/health` | `index_ready:true`, `api_key_configured:true`, `model_matches_index:true` |
| `GET /api/index` | Real manifest: 1 doc, 82 chunks, 3072 dims, 63 pages |
| `GET /api/sources` | Real NICE NG243 provenance, publisher, licence |
| `POST /api/search` | 3 results with real scores, pages, sections; 868 ms |
| `POST /api/search` (unrelated) | `out_of_scope`, 0 results |
| `POST /api/generate` | 5/5 clinical queries: evidence found, citations complete |
| `POST /api/generate` (unrelated) | 2/2 abstained in <900 ms, no LLM call |
| `POST /api/generate` (repeat) | `cache_hit=true`, 16 ms |
| `POST /api/generate/stream` | `meta` → 12 `token` events → `done`; citations complete |
| `POST /api/generate/stream` (cached) | Single token event replay — correct |
| `POST /api/generate/stream` (unrelated) | Abstains, 0 citations |

Final end-to-end run, no environment overrides — purely from committed `.env`:

```
=== GENERATE: clinical queries ===
  PASS |   5921ms | 1 cites | {'source_marker'}        | How should an adrenal crisis be managed
  PASS |   6834ms | 2 cites | {'source_marker'}        | What monitoring is needed during glucoco
  PASS |   6514ms | 2 cites | {'source_marker'}        | What steroid sick day rules apply during
  PASS |  69451ms | 1 cites | {'source_marker'}        | How is adrenal insufficiency identified
  PASS |  58777ms | 4 cites | {'fallback_all_sources'} | How should glucocorticoid withdrawal be
=== GENERATE: unrelated queries must abstain ===
  PASS |    858ms | abstained | how do I bake sourdough bread at home
  PASS |    823ms | abstained | what is the capital of Japan
=== CACHE ===
  PASS | cache_hit=True 16ms
RESULT: ALL PASS
```

Every citation carries document, section and page.

### CLI

| Command | Result |
|---|---|
| `cli query` | Works; shows real relevance; enforces scope |
| `cli eval` | 100% hit rate (18/18), target ≥80% — PASS |
| `cli benchmark` | Runs all retriever configs, emits the tracking matrix |
| `cli ingest` | **Not re-run** — would rebuild the index and spend embedding quota. Its fail-closed registry behaviour is covered by `tests/unit/test_registry.py`. |

### Frontend

Driven in a real browser against the live backend (`next dev` → `/api/*` → FastAPI):

- Page renders with live index stats (1 document, 82 chunks, real build timestamp).
- "Generate Answer" produced a grounded answer with inline `[Source 3, 1.7.5]` markers.
- Sources Cited rendered: **`[3] NICE NG243 — Adrenal insufficiency: identification
  and management / 1.7 Emergency management of adrenal crisis (Page 27)`** —
  document, section and page all present, no duplicated number.
- `tsc --noEmit` clean; `next build` clean (4/4 static pages).

### Tests and lint

```
173 passed, 1 warning
ruff: All checks passed!
```

Two new regression suites were added:

- `backend/tests/unit/test_citation_integrity.py` (5 tests) — covers the trailing-text
  marker, recommendation-id mapping, the never-empty guarantee, precedence order, and
  prompt/citation numbering alignment.
- `backend/tests/unit/test_scope_guardrail.py` (5 tests) — covers `absolute_relevance`
  precedence and all three scope states, including "unrelated query with score 1.0
  must be out_of_scope".

---

## 5. Files changed

**Backend**

| File | Change |
|---|---|
| `generation/client.py` | Explicit `"stream": False` |
| `generation/citations.py` | Relaxed marker regex; added `extract_recommendation_citations`, `resolve_citations`, `_to_citation`, `resolved_by` |
| `generation/assembler.py` | Extracted `select_sources` as the shared numbering contract |
| `generation/prompt.py` | Mandate `[Source N]`; forbid bare recommendation ids |
| `api/generate.py` | Use `select_sources` + `resolve_citations` on both paths |
| `models.py` | Added `RetrievalResult.absolute_relevance` |
| `retrieval/hybrid.py` | `below_floor` judged on absolute relevance |
| `retrieval/scope.py` | `classify_scope` compares absolute relevance |
| `config.py` | `RELEVANCE_FLOOR` 0.30 → 0.62; `SCOPE_THRESHOLD` 0.005 → 0.58, with measurements |
| `cli.py` | Applies scope guardrail; prints `rel=` |
| `tests/eval/test_generation_quality.py` | `get_retriever` → `get_shared_retriever` |
| `tests/unit/test_citation_integrity.py` | New (5 tests) |
| `tests/unit/test_scope_guardrail.py` | New (5 tests) |

**Frontend**

| File | Change |
|---|---|
| `lib/api.ts` | Added optional `resolved_by` to `Citation` |
| `components/AnswerCard.tsx` | Added `formatSection` to stop the duplicated section number |
| `lib/translations.ts` | Corrected the false 1536-dim claim (EN + AR) |

**Config**

| File | Change |
|---|---|
| `.env` | `GENERATION_MODEL=auto/chat`; `RELEVANCE_FLOOR=0.62`; added `SCOPE_THRESHOLD=0.58`. API key untouched. |
| `.env.example` | Synced to real config; documented the relevance-signal contract and how to check which models your gateway can serve |

---

## 6. Changes in the working tree that are not mine

`frontend/app/page.tsx`, and parts of `frontend/lib/api.ts` and
`frontend/components/AnswerCard.tsx`, contain edits that appeared during this session
and that I did not write — most likely from your editor:

- `page.tsx` — a fallback from `generateStream` to the non-streaming `generate` when
  streaming fails and nothing was received.
- `api.ts` — a `try/catch` around SSE frame parsing that ignores malformed frames.
- `AnswerCard.tsx` — styling changes (`text-ink-main` → `text-ink`, `border-line/60`),
  a `⚡` latency pill gated on `latency_ms > 0`, and a "Synthesizing…" loading state.

They typecheck, build, and pass alongside my changes, but I have not reviewed them for
correctness and am not claiming them. Worth a look before you commit — in particular
the `api.ts` catch will now swallow genuinely malformed frames silently.

---

## 7. Remaining recommendations

1. **Decide on the generation model.** `auto/chat` is a router; the underlying model
   varies per request, which is loose for a clinical tool. Getting gateway credentials
   for a pinned model would be better.
2. **Re-tune thresholds if the corpus grows.** 0.58/0.62 were measured against this
   single-document index. Adding documents shifts the cosine distribution; re-run the
   in-scope/out-of-scope measurement.
3. **Consider surfacing `resolved_by` in the UI.** A `fallback_all_sources` citation is
   block-level, not claim-level. Clinicians may want to see that distinction.
4. **Latency varies widely** (5.9 s to 69 s) because `auto/chat` routes to different
   backends. The cache makes repeats ~16 ms, but first-call latency is not predictable.
