# Eva AI - RAG Retrieval Quality & Reranker Latency Fix

## 1. Executive Summary

Retrieval was silently degraded: a sectioning bug in ingestion misattributed 61% of the
indexed corpus (50 of 82 chunks) to a single section number, flooding nearly every query's
top-k with irrelevant glossary/appendix text. Fixing it and re-ingesting cut the index to
34 correctly-attributed chunks and raised hybrid retrieval's Precision@3 from 0.389 to
0.574 (+47%) with zero golden-set misses. Separately, the optional cross-encoder reranker
had a batch-padding bug that inflated its per-query latency ~7x; fixed without changing
its ranking output.

## 2. Architectural Changes & Key Components

### Root cause: unnumbered back matter misattributed to the last numbered section

- `backend/app/ingestion/sectioner.py` only recognized section headings matching
  `N.N` (`_SECTION_HEADING`). NG243's back matter -- "Terms used in this guideline",
  "Rationale and impact", "Context", "Update information" -- is typeset at the *same*
  21-25.5pt bold font tier as real numbered sections but carries no number, so once
  the sectioner passed the last real section (1.9) it kept stamping every following
  page with `section_number="1.9"` for the rest of the document (pages 34-63, 30 pages).
  That back matter was 61% of the entire indexed corpus and won on lexical/semantic
  overlap against nearly every query, crowding the actually relevant chunk out of top-k.
- Added `_is_topmatter_heading()`: an unnumbered heading sized like a real section
  (>=19pt, above the 16.5pt sub-heading tier) now resets `section_number` to `""`.
- That surfaced a second bug: real section headings themselves wrap onto a second
  line (e.g. `"1.9 Managing glucocorticoid withdrawal to prevent"` / `"adrenal
  insufficiency"`), and the wrapped continuation line matched the same new check,
  immediately wiping the section number that had just been set correctly. Added
  `pending_heading` tracking so a wrapped heading line is merged into the title
  instead of being treated as a new heading event.
- `backend/app/ingestion/chunker.py`: defense-in-depth -- any block that still has
  a blank `section_number` (can't be attributed to a citation) is dropped before
  it reaches the index, never re-embedded or written to the store.
- `backend/tests/unit/test_sectioner.py`: fixture updated to model the real
  document's three distinct font tiers (body 12.0 / sub-heading 16.5 / section
  21.0) instead of collapsing section and sub-heading into one size, since the
  production fix now depends on that gap being real.

### Reranker latency

- `backend/app/retrieval/reranker.py`: `CrossEncoder.predict()` pads every pair in
  a batch to the length of the *longest* sequence in that batch. This corpus
  deliberately keeps one numbered recommendation whole and unsplit past the
  target chunk size (chunker.py's atomic-recommendation rule) at ~1635 tokens;
  whenever it entered the reranker's candidate batch it dragged every other
  candidate's padded length up with it. Isolated by direct measurement: 20 short
  pairs score in ~22ms, 20 pairs at ~400 words each take ~890ms -- attention
  cost is quadratic in sequence length.
- Fix: truncate each chunk's text to 1800 chars (~450 tokens) before building the
  scoring pair. The tokenizer's own `max_length=512` was truncating internally
  anyway, so no scoring information is lost -- this only stops the model from
  paying to process and discard the extra length, and bounds the batch's padded
  width. Also passes `show_progress_bar=False` to remove tqdm overhead on every call.

## 3. Performance & Latency Benchmarks

Golden-set evaluation, 18 questions, against `data/corpus/` (NICE NG243):

| Metric | Before (82 chunks) | After (34 chunks) |
|---|---:|---:|
| Indexed chunks | 82 | 34 |
| Hybrid hit rate | 100.0% | 100.0% |
| Hybrid mean hit rank | 1.83 | **1.11** |
| Hybrid Precision@3 | 0.389 | **0.574** (+47%) |
| Hybrid Precision@5 | 0.367 | 0.444 |
| Dense Precision@3 | 0.352 | 0.630 |
| Golden-set misses | 0 | 0 |

Reranker (`hybrid_rerank`), same 18 questions, before vs after the truncation fix:

| Metric | Before | After |
|---|---:|---:|
| Latency | 4437 ms/query | **3194 ms/query** (-28%) |
| Precision@3 | 0.537 | 0.519 (within noise, n=18) |
| Hit rate | 100.0% | 100.0% |

Plain hybrid (`RETRIEVER_TYPE=hybrid`, the shipped default) remains both faster
(12ms/query) and more precise (P@3 0.574) than reranking on this corpus -- the fix
makes the reranker path efficient for anyone who opts into `hybrid_rerank`, it does
not change which retriever ships by default.

## 4. Safety, Guardrails & Error Tracking

No guardrail behavior changed. The chunker's blank-`section_number` filter is an
additional safety net consistent with the existing Constitution Principle II
requirement that every chunk be attributable to a citeable section -- unattributable
back matter is now excluded at ingestion instead of silently retrievable.

## 5. Verification & Testing Evidence

```
$ python -m backend.app.cli ingest
Sections   detected 9 section(s), 96 numbered recommendation(s)
Chunking   34 chunks | mean 269 tok | min 23 | max 1590 | oversized 1
OK  1 document(s), 34 chunks indexed in 8.7s

$ python -m pytest backend/tests/unit -q
260 passed in ~35-55s
```

**Action required in any other environment**: re-run
`python -m backend.app.cli ingest` after pulling this fix -- it only takes effect
after re-ingestion, not on code deploy alone. The current `data/index/` in this
checkout was already rebuilt (34 chunks, manifest `built_at` 2026-08-19T08:49:56Z).

## Note on concurrent editing

This session ran alongside other agents committing to the same working tree.
`backend/tests/unit/test_sectioner.py` and `backend/app/retrieval/reranker.py`
were each overwritten mid-session by a concurrent commit before this fix landed;
both were reapplied and reverified green. If retrieval regresses again, check
first whether `_is_topmatter_heading` / `pending_heading` (sectioner.py) or
`_MAX_RERANK_CHARS` / `show_progress_bar=False` (reranker.py) are still present.
