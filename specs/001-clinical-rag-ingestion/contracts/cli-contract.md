# CLI Contract

**Feature**: 001-clinical-rag-ingestion

Entry point: `python -m backend.app.cli <command>` (FR-024).

---

## `ingest`

Rebuild the vector index from the registered corpus.

```bash
python -m backend.app.cli ingest [--dry-run] [--doc-id DOC_ID] [--verbose]
```

| Option | Effect |
|---|---|
| `--dry-run` | Parse, clean, and chunk, then report statistics without embedding or writing. No API cost. |
| `--doc-id` | Restrict to one registered document. |
| `--verbose` | Emit per-page diagnostics. |

**Preconditions**: `data/sources.yaml` exists; every PDF in `data/corpus/` is registered;
`OPENROUTER_API_KEY` is set (unless `--dry-run`).

**Behaviour**: builds a new collection and swaps it in on success. A failed run leaves the
previous index intact and queryable (FR-020).

**Output**

```text
Registry:  1 document registered, 1 PDF found, 0 unregistered
Parsing    nice_ng243 ... 63 pages, 5 front-matter skipped, 0 empty
Cleaning   removed 2 boilerplate patterns (126 line instances)
Sections   detected 8 sections, 47 numbered recommendations
Chunking   214 chunks | mean 587 tok | min 402 | max 796 | oversized 1
Embedding  214 chunks via openai/text-embedding-3-small ... done (11.3s)
Indexing   wrote 214 entries to data/index/ (collection: guidelines)
Manifest   data/index/manifest.json

OK  1 document, 214 chunks indexed in 24.1s
```

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unregistered PDF present in corpus (FR-002) |
| 2 | PDF has no extractable text layer |
| 3 | No sections detected in a document |
| 4 | Embedding provider error after retries |
| 5 | Configuration error (missing key, bad paths) |

---

## `query`

Retrieve chunks from the command line — the CLI half of FR-024.

```bash
python -m backend.app.cli query "What are the symptoms of adrenal insufficiency?" [--top-k 5] [--json] [--full-text]
```

**Output (default)**

```text
Query: What are the symptoms of adrenal insufficiency?
Model: openai/text-embedding-3-small | top_k=5 | floor=0.30

#1  0.847  NICE NG243  p.9   1.2 Initial identification and referral
    > When to suspect adrenal insufficiency  [rec 1.2.1]
    Consider adrenal insufficiency in people with unexplained hyperpigmentation...

#2  0.812  NICE NG243  p.10  1.2 Initial identification and referral
    ...

#5  0.264  NICE NG243  p.31  1.5 Management during psychological stress   [BELOW FLOOR]
    ...

evidence_found: true   (4 of 5 above floor)
```

Results below the relevance floor are shown and labelled, never hidden (FR-023,
Principle VI). `--json` emits the `SearchResponse` schema from `search-api.yaml`.

---

## `eval`

Run the golden question set and report retrieval quality.

```bash
python -m backend.app.cli eval [--top-k 5] [--json]
```

**Output**

```text
Golden set: 10 questions | top_k=5

  gq_01  HIT   rank 1  expected 1.2       What are the symptoms...
  gq_02  HIT   rank 2  expected 1.3       Which glucocorticoid...
  gq_03  MISS  --      expected 1.6       How is adrenal crisis...
  ...

Hit rate: 9/10 (90.0%)   target >= 80%   PASS
Mean rank of hits: 1.7
```

**Exit codes**: `0` when hit rate ≥ target (SC-003), `1` when below.

Equivalent assertions run under `pytest backend/tests/eval/` (FR-033).

---

## Configuration contract

All settings load from `.env` via `pydantic-settings` (D10). No magic numbers in modules.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required. Never committed. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Provider base URL |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Recorded in the manifest |
| `EMBEDDING_BATCH_SIZE` | `100` | Inputs per request |
| `GENERATION_MODEL` | `anthropic/claude-sonnet-4.5` | Day 2; unused in feature 001 |
| `CHUNK_TARGET_TOKENS` | `600` | Packing target |
| `CHUNK_MIN_TOKENS` | `400` | Floor |
| `CHUNK_MAX_TOKENS` | `800` | Ceiling; atomic recommendations may exceed it |
| `TOP_K` | `5` | Default retrieval depth |
| `RELEVANCE_FLOOR` | `0.30` | Below this, results are flagged not filtered |
| `CORPUS_DIR` | `data/corpus` | PDF location |
| `SOURCES_FILE` | `data/sources.yaml` | Provenance registry |
| `INDEX_DIR` | `data/index` | ChromaDB persistence |
| `CHROMA_COLLECTION` | `guidelines` | Collection name |
| `BOILERPLATE_PAGE_RATIO` | `0.6` | Line frequency above which text is boilerplate |
