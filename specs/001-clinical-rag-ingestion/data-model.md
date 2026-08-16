# Phase 1 — Data Model

**Feature**: 001-clinical-rag-ingestion | **Date**: 2026-08-16

Entities from [spec.md](spec.md) Key Entities, made concrete against the decisions in
[research.md](research.md).

---

## SourceDocument

A registered guideline PDF. Declared by hand in `data/sources.yaml`; never inferred.

| Field | Type | Required | Notes |
|---|---|---|---|
| `doc_id` | str | ✅ | Stable slug, e.g. `nice_ng243`. Used as the `chunk_id` prefix. |
| `document_name` | str | ✅ | Display title, e.g. `NICE NG243 — Adrenal insufficiency: identification and management` |
| `filename` | str | ✅ | Path relative to `data/corpus/` |
| `publisher` | str | ✅ | e.g. `National Institute for Health and Care Excellence (NICE)` |
| `publication_year` | int | ✅ | e.g. `2024` |
| `source_url` | str | ✅ | Public retrieval URL |
| `document_type` | enum | ✅ | `guideline` \| `bulletin` \| `review` \| `other` |
| `credibility_note` | str | ✅ | Written justification of why the source is credible and legally usable |
| `license_note` | str | ✅ | Terms of use / rights statement |

**Validation rules**
- Every PDF present in `data/corpus/` MUST have an entry, else ingestion fails (FR-002).
- `doc_id` is unique and matches `^[a-z0-9_]+$`.
- `credibility_note` must be non-empty and not a placeholder.
- `document_type != "guideline"` OR `publication_year < current_year - 10` ⇒ the document
  is marked `requires_caution`, which propagates to every chunk (FR-003, Principle III).

**Registered corpus**

```yaml
sources:
  - doc_id: nice_ng243
    document_name: "NICE NG243 — Adrenal insufficiency: identification and management"
    filename: "adrenal-insufficiency-identification-and-management-pdf-66143954919877.pdf"
    publisher: "National Institute for Health and Care Excellence (NICE)"
    publication_year: 2024
    source_url: "https://www.nice.org.uk/guidance/ng243"
    document_type: guideline
    credibility_note: >
      NICE is the statutory body producing evidence-based clinical guidance for the NHS
      in England. NG243 was published 28 August 2024 following formal evidence review and
      committee consensus. Published openly at nice.org.uk with no access restriction.
    license_note: >
      © NICE 2024. Subject to the NICE Notice of Rights. Reproduced here for
      non-commercial educational use within a hackathon prototype.
```

---

## Chunk

An indexed unit of guideline text. One ChromaDB entry each.

| Field | Type | Required | Notes |
|---|---|---|---|
| `chunk_id` | str | ✅ | Chroma primary id. Format `{doc_id}_p{page}_c{seq:02d}`, e.g. `nice_ng243_p09_c03` |
| `text` | str | ✅ | Cleaned chunk text — the embedded content |
| `document_name` | str | ✅ | Denormalised from SourceDocument |
| `doc_id` | str | ✅ | Filter key |
| `page_number` | int | ✅ | 1-indexed **source PDF** page, for human trace-back |
| `section_title` | str | ✅ | e.g. `1.2 Initial identification and referral` |
| `section_number` | str | ✅ | e.g. `1.2`. Empty string when unnumbered. |
| `subsection_title` | str | ✅ | Prose sub-heading, e.g. `When to suspect adrenal insufficiency`. Empty string if none. |
| `recommendation_ids` | str | ✅ | Comma-joined, e.g. `1.2.1,1.2.2`. Empty string for narrative chunks. |
| `source_url` | str | ✅ | Denormalised |
| `document_type` | str | ✅ | Denormalised |
| `publication_year` | int | ✅ | Denormalised |
| `requires_caution` | bool | ✅ | Denormalised; drives the UI flag |
| `token_count` | int | ✅ | tiktoken `cl100k_base` |
| `is_oversized` | bool | ✅ | True when an atomic recommendation exceeded the ceiling |

**Validation rules**
- All fields non-null. Optional-by-meaning fields use `""`, never `None` — Chroma
  metadata rejects nulls (FR-015).
- `chunk_id` unique across the collection.
- `400 ≤ token_count ≤ 800` unless `is_oversized` (FR-012, FR-014).
- A numbered recommendation appears in exactly one chunk (FR-011, SC-006).
- Metadata is written to the Chroma entry itself — never a sidecar (FR-017,
  Principle II).

**Chroma mapping**: `text` → `documents`, `chunk_id` → `ids`, every other field →
`metadatas`. Values must be scalar (str/int/float/bool), which the flat shape above
guarantees.

---

## IndexManifest

Written to `data/index/manifest.json` on every ingest. Makes an index self-describing.

| Field | Type | Notes |
|---|---|---|
| `built_at` | datetime | ISO 8601 UTC |
| `embedding_model` | str | e.g. `openai/text-embedding-3-small` (FR-019) |
| `embedding_dimensions` | int | e.g. `1536` |
| `chunk_target_tokens` | int | Config snapshot |
| `chunk_min_tokens` | int | Config snapshot |
| `chunk_max_tokens` | int | Config snapshot |
| `document_count` | int | |
| `chunk_count` | int | |
| `oversized_chunk_count` | int | |
| `per_document` | list | `{doc_id, pages_processed, pages_empty, chunk_count}` (FR-009) |

**Validation rule**: at query time, if `manifest.embedding_model` differs from the
configured model, the API returns an error rather than mixing vector spaces.

---

## RetrievalResult

A Chunk paired with its score for one query. Not persisted.

| Field | Type | Notes |
|---|---|---|
| `chunk` | Chunk | Full chunk with metadata |
| `score` | float | Cosine similarity, `1 - distance`, range 0–1 |
| `rank` | int | 1-indexed |
| `below_floor` | bool | `score < relevance_floor` — flagged, never filtered (FR-023) |

---

## GoldenQuestion

Evaluation fixture in `backend/tests/eval/golden_questions.yaml`.

| Field | Type | Notes |
|---|---|---|
| `id` | str | e.g. `gq_01` |
| `question` | str | Natural-language clinical question |
| `expected_doc_id` | str | Expected source document |
| `expected_sections` | list[str] | Any one counts as a hit, e.g. `["1.2"]` |
| `expected_recommendation_ids` | list[str] | Optional, stricter assertion |
| `notes` | str | Why this is the right answer |

**Validation rules**: ≥10 entries (FR-031); every `expected_doc_id` is registered.

---

## Entity Relationships

```text
SourceDocument (1) ──< (many) Chunk
       │                        │
       │                        └──< (many) RetrievalResult   [per query, transient]
       │
       └──< referenced by GoldenQuestion.expected_doc_id

IndexManifest (1) ── describes ──> the whole Chunk collection
```

---

## State Transitions — ingestion

```text
registered → parsed → cleaned → sectioned → chunked → embedded → indexed
     │          │         │          │          │          │
     │          │         │          │          │          └─ fail: provider error → abort, index untouched
     │          │         │          │          └─ fail: oversized → emit flagged, continue
     │          │         │          └─ fail: no sections found → abort with diagnostic
     │          │         └─ fail: page empty after cleaning → count, skip page, continue
     │          └─ fail: no text layer → abort with diagnostic (scanned PDF)
     └─ fail: unregistered file → abort before any parsing (FR-002)
```

Ingestion is **atomic at the collection level**: the new collection is built, then swapped
in. A failed run leaves the previous index intact and queryable (FR-020).
