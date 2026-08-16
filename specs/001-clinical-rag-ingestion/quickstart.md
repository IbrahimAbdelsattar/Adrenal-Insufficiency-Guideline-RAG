# Quickstart & Validation Guide

**Feature**: 001-clinical-rag-ingestion | **Date**: 2026-08-16

How to run the system and prove it satisfies the Day 1 gates. Schemas live in
[contracts/](contracts/); entity definitions in [data-model.md](data-model.md).

---

## Prerequisites

| Requirement | Verified present |
|---|---|
| Python 3.13 | ✅ 3.13.12 |
| Node.js 20+ | ✅ 24.12.0 |
| npm | ✅ 11.6.2 |
| OpenRouter API key | Required — supply in `.env` |
| NICE NG243 PDF | ✅ present in repository root, moves to `data/corpus/` |

No Docker, no database server, no GPU.

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

Then copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.

---

## Build the index

Validate parsing and chunking with no API spend first:

```bash
python -m backend.app.cli ingest --dry-run --verbose
```

Then build for real:

```bash
python -m backend.app.cli ingest
```

Expected: ~200 chunks from 63 pages in under 10 minutes (SC-001).

---

## Run the application

Backend:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000`. Requests to `/api/*` are rewritten to port 8000.

---

## Validation scenarios

Each maps to acceptance criteria in [spec.md](spec.md). Run all before declaring Day 1
complete.

### V1 — Ingestion produces a populated, fully-attributed index

*Covers US1, FR-001→FR-020, SC-002*

```bash
python -m backend.app.cli ingest
```

Pass when: exit code 0; chunk count > 0; the summary reports per-document pages processed
and empty; `data/index/manifest.json` records the embedding model.

Then confirm every chunk carries complete metadata — zero fields empty across
`document_name`, `page_number`, `section_title`, `chunk_id`, `source_url` (SC-002).

### V2 — Unregistered sources are rejected

*Covers FR-002, Principle III*

Place any unregistered PDF in `data/corpus/` and re-run ingest. Pass when it exits `1`
and names the offending file. Remove the file afterwards.

### V3 — Retrieval returns ranked, attributed evidence

*Covers US2, FR-021→FR-025, SC-007*

```bash
python -m backend.app.cli query "What are the symptoms of adrenal insufficiency?"
```

Pass when: results are ranked by descending score; each shows document, page, and
section; results below the floor appear labelled rather than hidden; total time under 3
seconds.

### V4 — Web inspector shows the demo path

*Covers US2, FR-026→FR-030, the brief's demo gate*

In the browser, submit the same question. Pass when each result card shows score,
document name, page number, section title, and full text; the index status panel shows
document and chunk counts; the decision-support disclaimer is visible.

**This is the end-of-day demo: question → top chunks → source page and section.**

### V5 — Golden set meets the quality target

*Covers US3, FR-031→FR-033, SC-003*

```bash
python -m backend.app.cli eval
```

Pass when hit rate ≥ 80% (≥8 of 10 questions retrieve their expected section within
top-5). Equivalent assertion:

```bash
pytest backend/tests/eval/ -v
```

### V6 — Chunks are coherent standalone *(manual — Principle VI)*

*Covers SC-005, the brief's "open 5 chunks" gate*

Sample 5 chunks at random and read each in isolation. Pass when all 5 convey a complete
clinical idea with no dangling references and no leftover header/footer noise.

### V7 — Chunks trace back to the source PDF *(manual — Principle VI)*

*Covers SC-004*

Take any chunk, note its `page_number`, open the PDF at that page. Pass when the text is
found there verbatim.

### V8 — No recommendation is split across chunks

*Covers FR-011, SC-006*

Verify that each numbered recommendation id appears in exactly one chunk's
`recommendation_ids`. Pass when there are zero duplicates.

### V9 — Generation is correctly absent

*Covers FR-034, Principle V*

```bash
curl -X POST http://localhost:8000/api/generate -H "Content-Type: application/json" -d "{\"query\":\"test\"}"
```

Pass when it returns **501** with an explanatory message. A 200 here means Principle V has
been violated.

### V10 — Empty-index behaviour is graceful

*Covers US2 scenario 5, FR-025*

Temporarily move `data/index/` aside, then query. Pass when the API returns 503 with a
clear message and the UI states that no evidence is available — no stack trace, no silent
empty page. Restore the directory afterwards.

---

## Full test suite

```bash
pytest backend/tests/ -v
```

---

## Gate checklist

Copy into the end-of-day review. All must pass before Day 2.

| Gate | Scenario |
|---|---|
| PDFs official and public | V2 + registry review |
| Scope narrow, stated in one sentence | spec.md Scope Statement |
| Source URLs and names recorded | `GET /api/sources` |
| Licensing addressed | registry `license_note` |
| Chunks readable standalone | V6 |
| Page and section preserved | V1, V3 |
| Recommendations split correctly | V8 |
| Extraction noise removed | V6 |
| Embeddings created, model documented | V1 manifest |
| Metadata returned with chunks | V3, V4 |
| 10 questions retrieve reasonable evidence | V5 |
| Weak results visible | V3 |
| **Demo: question → chunks → page/section** | **V4** |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `exit 1` naming a PDF | Unregistered source | Add it to `data/sources.yaml` or remove it |
| `exit 2` no text layer | Scanned PDF | Out of scope — OCR is not supported |
| `exit 4` after retries | Provider error or rate limit | Check key and credit; lower `EMBEDDING_BATCH_SIZE` |
| 503 on search | Index missing or empty | Run `ingest` |
| Model-mismatch error | Index built with a different model | Re-run `ingest` after changing `EMBEDDING_MODEL` |
| Chunks contain footer text | Boilerplate threshold too high | Lower `BOILERPLATE_PAGE_RATIO` |
| Many oversized chunks | Recommendations exceed the ceiling | Raise `CHUNK_MAX_TOKENS`; never truncate |
| Low hit rate | Chunking or embedding quality | Day 2 work — hybrid search or reranking |
