# Eva AI — Checklist-to-Code Implementation Guide

> **Purpose:** This file maps the hackathon checklists to the exact places where each requirement is implemented in the Eva AI project.
>
> **Audit basis:** static inspection of the submitted project repository (`Eva-AI-main`) and the Day 1–4 curriculum/checklist material supplied with the project.
>
> **Important:** `Implemented` means the corresponding production code or test was found in the repository. `Partial / different implementation` means the checklist requirement exists, but the project implements it differently from the wording/example in the training material. `Docs only` means the requirement is described/documented but no matching production implementation was found during this audit.

---

## 0. Quick Project Map

| Area | Main location | What it contains |
|---|---|---|
| Clinical source registration | `data/sources.yaml` | Approved PDF metadata, publisher, URL, license/credibility notes |
| Source PDF | `data/corpus/` | NICE NG243 guideline PDF |
| PDF parsing | `backend/app/ingestion/parser.py` | Structured PDF extraction |
| Text cleaning | `backend/app/ingestion/cleaner.py` | Boilerplate, line-break, glyph and formatting cleanup |
| Section detection | `backend/app/ingestion/sectioner.py` | Section / subsection / recommendation detection |
| Chunking | `backend/app/ingestion/chunker.py` | Section-aware and fixed-size chunking |
| Ingestion orchestration | `backend/app/ingestion/pipeline.py` | Parse → clean → section → chunk → embed → index |
| Data model / provenance | `backend/app/models.py` | Chunk metadata, retrieval result, request/response models |
| Embeddings | `backend/app/embeddings/` | OpenRouter, local and fallback embedding implementations |
| Vector database | `backend/app/retrieval/store.py` | ChromaDB collections, indexing and retrieval |
| Dense retrieval | `backend/app/retrieval/dense.py` | Semantic vector search |
| BM25 retrieval | `backend/app/retrieval/bm25.py` | Lexical search |
| Hybrid retrieval | `backend/app/retrieval/hybrid.py` | Dense + BM25 RRF fusion |
| Reranking | `backend/app/retrieval/reranker.py` | Cross-encoder reranking + fallback |
| Retrieval factory/config | `backend/app/retrieval/factory.py`, `backend/app/config.py` | Retriever selection and thresholds |
| Scope guard | `backend/app/retrieval/scope.py` | In-scope / no-evidence / out-of-scope classification |
| Prompt injection guard | `backend/app/generation/guardrails.py` | Deterministic injection/jailbreak detection |
| Grounding prompt | `backend/app/generation/prompt.py` | Evidence-only generation rules and citation requirements |
| Evidence assembly | `backend/app/generation/assembler.py` | Numbered evidence blocks passed to the LLM |
| Citation extraction/validation | `backend/app/generation/citations.py` | `[Source N]` parsing, claim-level grounding validation |
| Generation pipeline | `backend/app/generation/service.py` | Retrieval → scope → graph → cache → prompt → LLM → grounding |
| API | `backend/app/api/generate.py`, `backend/app/api/search.py` | Search/generation JSON + SSE endpoints |
| Retrieval evaluation | `backend/app/evaluation.py` | Hit Rate, Mean Hit Rank, Precision@3, Precision@5 |
| Golden questions | `backend/tests/eval/golden_questions.yaml` | 18 clinical retrieval questions |
| Retrieval tests | `backend/tests/eval/test_retrieval_quality.py` + integration/unit tests | Retrieval regression tests |
| Generation tests | `backend/tests/eval/test_generation_quality.py` + unit tests | Grounding/generation regression tests |
| Frontend answer | `frontend/components/AnswerCard.tsx` | Answer, grounding status, citations, cache/latency badges |
| Evidence inspector | `frontend/components/chat/EvidencePanel.tsx` | Document, section, page, score and retrieved text |
| Chat history | `frontend/hooks/useChatSessions.ts`, `frontend/components/chat/ChatHistory.tsx` | Persistent consultation sessions |
| Observability | `backend/app/monitoring/`, `frontend/sentry*.config.ts`, `frontend/instrumentation.ts` | Metrics, tracing, Sentry, PHI-safe logging |

---

# 1. Day 1 — Sources, Ingestion and Retrieval Foundation

The Day 1 curriculum requires an official guideline, reliable PDF ingestion, section-aware chunking, embeddings, vector indexing and provenance metadata.

## 1.1 Select 1–2 official guideline PDFs

**Status: Implemented**

### Where

- `data/corpus/adrenal-insufficiency-identification-and-management-pdf-66143954919877.pdf`
- `data/sources.yaml`

### Implementation

`data/sources.yaml` registers the NICE NG243 guideline with:

- `doc_id`
- exact document name
- filename
- publisher
- publication year
- source URL
- document type
- credibility note
- license note

The ingestion registry validates that PDFs in the corpus are registered before ingestion proceeds.

### Supporting code

- `backend/app/models.py` → `SourceDocument`
- `backend/app/ingestion/registry.py` → corpus validation
- `backend/app/ingestion/pipeline.py` → fail-closed registry validation

---

## 1.2 Public accessibility / legal usability / scope documentation

**Status: Implemented as source metadata + registry controls**

### Where

- `data/sources.yaml`
- `backend/app/models.py`
- `backend/app/ingestion/registry.py`

### Notes

The project explicitly records credibility and license justification. Placeholder justification values are rejected by `SourceDocument` validation.

The project currently uses NICE NG243 as the registered guideline.

---

## 1.3 Parse PDF content

**Status: Implemented**

### Where

- `backend/app/ingestion/parser.py`
- `backend/app/ingestion/pipeline.py`

### Flow

```text
registered PDF
   ↓
parser.parse_pdf()
   ↓
ParsedPage objects
   ↓
cleaner.clean()
```

`pipeline.py` is the orchestration point that calls the parser before cleaning and section detection.

---

## 1.4 Clean extracted PDF text

**Status: Implemented**

### Where

- `backend/app/ingestion/cleaner.py`

### Handles

- malformed bullet glyphs
- soft line breaks
- hyphenation across lines
- table-of-contents lines
- page-number-only lines
- repeated headers/footers / boilerplate
- whitespace normalization

This is an important prerequisite for reliable chunking and retrieval.

---

## 1.5 Section-aware chunking

**Status: Implemented**

### Where

- `backend/app/ingestion/sectioner.py`
- `backend/app/ingestion/chunker.py`
- `backend/app/config.py`

### Main implementation

`chunk_blocks_section()` packs blocks by section/subsection and keeps numbered recommendations atomic.

Configured defaults in `backend/app/config.py`:

- target: `600` tokens
- minimum: `400` tokens
- maximum: `800` tokens

The chunker also:

- prevents section mixing
- preserves recommendation IDs
- keeps oversized recommendations whole and flags them
- removes navigational cross-reference stubs
- preserves page and section provenance

### Comparison implementation

`chunk_blocks_fixed()` also exists for the Day 2 experimental comparison:

- fixed window
- 256-token default
- 10% overlap

So the project supports both the experimental baseline and the chosen section-aware strategy.

---

## 1.6 Generate embeddings

**Status: Implemented**

### Where

`backend/app/embeddings/`

Files:

- `base.py`
- `openrouter.py`
- `local.py`
- `fallback.py`

### Integration

`backend/app/ingestion/pipeline.py` embeds chunks in batches before indexing them.

The pipeline also supports a local fallback collection when configured.

---

## 1.7 Index chunks in vector database

**Status: Implemented**

### Where

- `backend/app/retrieval/store.py`
- `backend/app/ingestion/pipeline.py`
- `backend/app/config.py`

### Technology

ChromaDB is used for the vector store.

`VectorStore.build()` writes chunk IDs, chunk text, embeddings and scalar metadata to the collection.

The ingestion pipeline rebuilds the index and protects the existing index from failed ingestion by only completing the swap after successful processing.

---

## 1.8 Store document / section / page metadata

**Status: Implemented**

### Where

`backend/app/models.py` → `Chunk`

Metadata includes:

- `document_name`
- `doc_id`
- `source_url`
- `document_type`
- `publication_year`
- `page_number`
- `section_title`
- `section_number`
- `subsection_title`
- `recommendation_ids`
- `token_count`
- `is_oversized`
- `requires_caution`

`Chunk.to_metadata()` is the canonical metadata serialization point.

---

## 1.9 Day 1 end-of-day retrieval-ready corpus

**Status: Implemented**

### Evidence in code

`backend/app/ingestion/pipeline.py` produces an `IndexManifest` containing:

- embedding model
- embedding dimensions
- chunk configuration
- document count
- chunk count
- oversized chunk count
- per-document statistics

### Main file

`backend/app/models.py` → `IndexManifest`

---

# 2. Day 2 — Retrieval Optimization Checklist

Day 2 focuses on Top-K, chunk tuning, semantic/keyword/hybrid retrieval, evaluation and evidence transparency.

## 2.1 Top-K retrieval

**Status: Implemented**

### Where

- `backend/app/config.py` → `TOP_K`
- `backend/app/retrieval/store.py`
- `backend/app/retrieval/dense.py`
- `backend/app/retrieval/bm25.py`
- `backend/app/retrieval/hybrid.py`
- `backend/app/api/search.py`
- `backend/app/api/generate.py`

The current project default is `TOP_K=3`, based on the project's Day 2 benchmark.

The system still allows the request to override `top_k`.

---

## 2.2 Compare Top-3 / Top-5 / Top-10

**Status: Implemented**

### Where

- `backend/app/evaluation.py`
- `backend/tests/eval/golden_questions.yaml`
- `DAY2_RETRIEVAL_OPTIMIZATION.md`

The evaluator calculates Precision@3 and Precision@5 and supports configurable `top_k`.

The Day 2 report documents comparison across `k = 3, 5, 10`.

---

## 2.3 Tune chunk size and overlap

**Status: Implemented**

### Where

- `backend/app/ingestion/chunker.py`
- `backend/app/config.py`
- `DAY2_RETRIEVAL_OPTIMIZATION.md`

Two strategies exist for empirical comparison:

1. fixed-size chunks
2. section-aware recommendation packing

The project selected section-aware chunking as the standard implementation.

---

## 2.4 Semantic retrieval

**Status: Implemented**

### Where

- `backend/app/retrieval/dense.py`
- `backend/app/retrieval/store.py`

Dense retrieval uses embedding similarity against the ChromaDB collection.

---

## 2.5 Keyword retrieval / BM25

**Status: Implemented**

### Where

- `backend/app/retrieval/bm25.py`

The implementation uses BM25-style lexical retrieval and preserves clinical terms, drug names, dosages and section information in the searchable representation.

---

## 2.6 Hybrid retrieval

**Status: Implemented**

### Where

- `backend/app/retrieval/hybrid.py`
- `backend/app/retrieval/factory.py`
- `backend/app/config.py`

The project supports:

- dense
- BM25
- hybrid Dense + BM25 RRF
- hybrid + reranking

Current default:

```text
RETRIEVER_TYPE=hybrid
```

---

## 2.7 Cross-encoder reranking

**Status: Implemented, but disabled by default**

### Where

- `backend/app/retrieval/reranker.py`
- `backend/app/retrieval/hybrid.py`
- `backend/app/retrieval/factory.py`
- `backend/app/config.py`

The reranker has a graceful fallback if the model cannot load or inference fails.

The Day 2 project report records that plain hybrid retrieval performed better on the project's benchmark, so the default is currently plain hybrid rather than reranked hybrid.

---

## 2.8 Retrieval confidence / relevance floor

**Status: Implemented**

### Where

- `backend/app/config.py` → `RELEVANCE_FLOOR`, `SCOPE_THRESHOLD`
- `backend/app/models.py` → `RetrievalResult.absolute_relevance`
- `backend/app/retrieval/scope.py`
- `backend/app/retrieval/hybrid.py`

Important design detail:

The system does **not** use the normalized RRF ranking score as an absolute confidence value. It uses an absolute relevance signal such as dense cosine or reranker score.

---

## 2.9 Mini/golden evaluation set

**Status: Implemented**

### Where

- `backend/tests/eval/golden_questions.yaml`
- `backend/app/evaluation.py`
- `backend/tests/eval/test_retrieval_quality.py`

The repository contains 18 golden clinical retrieval questions covering major NG243 recommendation areas.

---

## 2.10 Precision@K

**Status: Implemented**

### Where

`backend/app/evaluation.py`

Implemented metrics include:

- Hit Rate
- Mean Hit Rank
- Mean Precision@3
- Mean Precision@5

The evaluator also creates per-question retrieval inspection records with page, section, recommendation IDs, score and relevance.

---

## 2.11 Retrieval failure analysis

**Status: Implemented**

### Where

`backend/app/evaluation.py`

The evaluator produces notes such as:

- missed target section
- semantic drift in lower ranks
- high-precision evidence captured

The Day 2 report also documents failure modes and experimental results.

---

## 2.12 Evidence panel before/around generation

**Status: Implemented**

### Where

- `frontend/components/chat/EvidencePanel.tsx`
- `frontend/components/ChunkCard.tsx`
- `frontend/components/AnswerCard.tsx`

The UI can display:

- document name
- section number/title
- page
- retrieval score
- source URL
- recommendation relationship
- excerpt/full chunk
- retrieval timestamp
- weak-match/caution badges

This directly supports the Day 2 requirement that retrieval be inspectable rather than hidden.

---

# 3. Day 3 — Grounded Generation & Citation Checklist

## 3.1 Strict grounding system prompt

**Status: Implemented**

### Where

`backend/app/generation/prompt.py`

`SYSTEM_PROMPT` explicitly enforces:

- evidence-only generation
- mandatory citations
- no outside medical knowledge
- exact drug names/doses/values from evidence
- explicit abstention when evidence is insufficient
- resistance to prompt injection/persona manipulation
- no system prompt disclosure

---

## 3.2 Pass retrieved evidence into the prompt

**Status: Implemented**

### Where

- `backend/app/generation/assembler.py`
- `backend/app/generation/prompt.py`
- `backend/app/generation/service.py`
- `backend/app/api/generate.py`

The evidence assembler creates numbered evidence blocks. The prompt then receives those exact blocks.

Citation numbering is therefore tied to the evidence actually shown to the LLM.

---

## 3.3 Recommendation / evidence / citation response structure

**Status: Implemented with a project-specific format**

The training material describes a structured recommendation/evidence/citation format. Eva AI implements this through:

- grounded evidence blocks
- inline `[Source N]` citations
- structured citation objects in the API
- a separate evidence panel in the UI

### Main locations

- `backend/app/generation/prompt.py`
- `backend/app/generation/assembler.py`
- `backend/app/generation/citations.py`
- `backend/app/models.py`
- `frontend/components/AnswerCard.tsx`
- `frontend/components/chat/EvidencePanel.tsx`

### Important difference

The training slide references a ready-made `schema/response_schema.json`, but **that exact file does not exist in this project archive**.

Instead, the project uses Pydantic response models in `backend/app/models.py` plus deterministic citation/grounding validation in `backend/app/generation/citations.py`.

---

## 3.4 Citation format: document + section + page

**Status: Implemented**

### Where

- `backend/app/generation/citations.py`
- `backend/app/models.py`
- `frontend/components/AnswerCard.tsx`
- `frontend/components/chat/EvidencePanel.tsx`

Citation objects contain the source document, section information and page number, together with the source text/excerpt and relevance metadata.

The UI renders the document, section and page alongside the citation.

---

## 3.5 Citation marker resolution

**Status: Implemented**

### Where

`backend/app/generation/citations.py`

The parser:

1. detects `[Source N]`
2. deduplicates markers
3. maps the marker to the exact retrieved evidence block
4. converts it to a structured citation object
5. preserves provenance metadata for the UI

Recommendation-number citations can also be resolved when applicable.

---

## 3.6 Claim-level grounding validation

**Status: Implemented**

### Where

`backend/app/generation/citations.py`

`validate_grounding()` rejects generated answers when:

- citation markers are invalid
- clinical claims lack citations
- dosage/route/timing/threshold/emergency claims are uncited
- the model cites evidence it was not actually shown

This is stronger than merely checking whether an answer contains *some* citation.

---

## 3.7 Prompt-injection / adversarial defense

**Status: Implemented**

### Where

- `backend/app/generation/guardrails.py`
- `backend/app/api/generate.py`
- `backend/tests/unit/test_grounding_stress.py`
- `backend/tests/unit/test_scope_guardrail.py`

The guard catches common patterns such as:

- ignore previous instructions
- override rules
- jailbreak/DAN
- developer mode
- reveal system prompt
- role switching
- instruction delimiter attacks

It runs before retrieval/LLM generation.

---

## 3.8 Refusal when there is no useful evidence

**Status: Implemented**

### Where

- `backend/app/generation/citations.py` → `should_abstain()`
- `backend/app/retrieval/scope.py`
- `backend/app/generation/service.py`
- `backend/app/api/generate.py`

The generation path can abstain for:

- out-of-scope questions
- no supporting evidence
- weak retrieval
- prompt injection
- greeting/capability requests before clinical retrieval
- grounding validation failure

---

## 3.9 Rehearsed refusal test case

**Status: Implemented / documented**

### Where

- `backend/tests/eval/DAY5_REFUSAL_TEST_CASE.md`
- `docs/refusal_test_case_day5.md`
- `backend/tests/unit/test_grounding_stress.py`
- `backend/tests/unit/test_scope_guardrail.py`

The repository contains dedicated refusal test documentation and automated tests around grounding/scope behavior.

---

# 4. Day 4 — Safety, Guardrails & Internal Evaluation Checklist

## 4.1 Input risk classification

**Status: Implemented, but not as a separate ML classifier**

### Where

- `backend/app/retrieval/scope.py`
- `backend/app/generation/guardrails.py`
- `backend/app/generation/clarification.py`
- `backend/app/generation/service.py`

The project uses deterministic routing rather than a standalone `RiskClassifier` model.

Implemented decisions include:

- `in_scope`
- `no_evidence`
- `out_of_scope`
- prompt injection refusal
- clarification for ambiguous cases

### Supporting test files

- `backend/tests/unit/test_scope.py`
- `backend/tests/unit/test_scope_guardrail.py`
- `backend/tests/unit/test_clarification.py`
- `backend/tests/unit/test_greeting_guardrail.py`

---

## 4.2 Retrieval confidence threshold gate

**Status: Implemented**

### Where

- `backend/app/config.py`
- `backend/app/models.py`
- `backend/app/retrieval/scope.py`
- `backend/app/retrieval/hybrid.py`

The system calculates an absolute relevance signal and compares it against configurable thresholds before allowing evidence to proceed.

---

## 4.3 Unsupported claim detection

**Status: Implemented**

### Where

`backend/app/generation/citations.py`

This is implemented as post-generation grounding validation.

The validator identifies clinical claim shapes involving:

- doses
- routes
- timing/frequency
- lab/vital thresholds
- emergency instructions

An unsupported clinical claim causes the answer to be withheld rather than displayed.

---

## 4.4 Citation accuracy

**Status: Implemented structurally + tested**

### Where

- `backend/app/generation/citations.py`
- `backend/tests/unit/test_citations.py`
- `backend/tests/unit/test_citation_integrity.py`

The system resolves citations only against evidence blocks actually supplied to the model.

The UI additionally exposes the exact document/section/page/chunk provenance.

---

## 4.5 Citation coverage / claim faithfulness

**Status: Implemented as deterministic validation; formal aggregate metric is not clearly exposed as a dedicated production metric**

### Implemented

- claim-level citation enforcement
- unsupported-claim detection
- grounding status: `verified`, `failed`, `abstained`

### Main file

`backend/app/generation/citations.py`

### Important distinction

The Day 4 curriculum describes aggregate metrics such as:

```text
Citation coverage
Claim faithfulness
Unsupported claim rate
```

The project has the **mechanism** needed to enforce these properties, but the main retrieval evaluator in `backend/app/evaluation.py` focuses on retrieval metrics. Do not describe the project as having a dedicated aggregate faithfulness dashboard unless another evaluation script/report is being used.

---

## 4.6 Internal evaluation dataset

**Status: Implemented**

### Where

- `backend/tests/eval/golden_questions.yaml`
- `backend/tests/eval/golden_generation.yaml`
- `backend/tests/eval/test_generation_quality.py`
- `backend/tests/eval/test_retrieval_quality.py`

There are separate golden datasets for retrieval and generation.

---

## 4.7 Safety refusal tests

**Status: Implemented**

### Where

- `backend/tests/unit/test_grounding.py`
- `backend/tests/unit/test_grounding_stress.py`
- `backend/tests/unit/test_scope_guardrail.py`
- `backend/tests/eval/DAY5_REFUSAL_TEST_CASE.md`
- `docs/refusal_test_case_day5.md`

---

## 4.8 Clinical safety disclaimer

**Status: Implemented**

### Where

- `backend/app/models.py` → `DISCLAIMER`
- `backend/app/api/generate.py`
- `backend/app/api/search.py`
- frontend response rendering

The API includes a disclaimer in generated/search responses and the README explicitly frames Eva AI as a decision-support research prototype rather than a diagnostic or emergency system.

---

## 4.9 Safe UX states

**Status: Implemented**

### Where

- `frontend/components/AnswerCard.tsx`
- `frontend/components/chat/EvidencePanel.tsx`
- `frontend/components/chat/ChatMessage.tsx`
- `frontend/components/ChatView.tsx`

The UI exposes states such as:

- verified grounding
- failed grounding / unverified answer
- no answer / abstained
- insufficient evidence
- weak match
- non-current source
- cached response
- latency

---

## 4.10 Evidence must be visible to the user

**Status: Implemented**

### Where

`frontend/components/chat/EvidencePanel.tsx`

The evidence inspector shows:

- source/document
- section
- page
- retrieval score
- source URL
- evidence excerpt
- full guideline chunk
- citation type
- weak-match indicator
- source age/caution information

---

# 5. Additional Day 4 / Production Enhancements

These are not merely checklist basics; they are extra project implementations that strengthen the final system.

## 5.1 Conversation history

**Implemented**

### Where

- `frontend/hooks/useChatSessions.ts`
- `frontend/components/chat/ChatHistory.tsx`
- `frontend/components/chat/ChatMessage.tsx`
- `frontend/components/chat/SessionExport.tsx`
- `backend/app/models.py`
- `backend/app/generation/prompt.py`

Recent conversation turns are included in generation context, while the frontend keeps consultation sessions.

---

## 5.2 Response caching

**Implemented**

### Where

- `backend/app/retrieval/cache.py`
- `backend/app/generation/service.py`
- `backend/app/api/search.py`
- `frontend/components/AnswerCard.tsx`

There are response/retrieval/embedding cache layers and cache invalidation tied to the index manifest.

---

## 5.3 SSE streaming

**Implemented**

### Where

- `backend/app/api/generate.py`
- `frontend/hooks/useStreamingChat.ts`
- `frontend/lib/api.ts`

The stream exposes metadata, generated tokens and final citation/latency information.

---

## 5.4 Lightweight Graph RAG

**Implemented**

### Where

- `backend/app/graph.py`
- `backend/app/generation/service.py`
- `backend/app/config.py`

The graph links chunks by section and recommendation IDs, then can add one adjacent evidence chunk to the retrieved set.

---

## 5.5 Observability / tracing

**Implemented**

### Where

- `backend/app/monitoring/logging_config.py`
- `backend/app/monitoring/metrics.py`
- `backend/app/monitoring/sentry.py`
- `frontend/sentry.client.config.ts`
- `frontend/sentry.server.config.ts`
- `frontend/sentry.edge.config.ts`
- `frontend/instrumentation.ts`
- `frontend/app/global-error.tsx`

The backend traces retrieval, reranking, generation and other RAG stages.

---

## 5.6 PHI / sensitive-query logging protection

**Implemented**

### Where

- `backend/app/config.py`
- `backend/app/monitoring/sentry.py`
- `backend/app/monitoring/logging_config.py`

The configuration supports query text truncation/suppression and prompt-preview controls. Sentry integration includes sanitization logic.

---

## 5.7 Rate limiting

**Implemented**

### Where

- `backend/app/ratelimit.py`
- `backend/app/ratelimit_test.py`

---

# 6. Test Checklist → Test File Map

| Requirement | Main test location |
|---|---|
| Chunking | `backend/tests/unit/test_chunker.py` |
| Section detection | `backend/tests/unit/test_sectioner.py` |
| Cleaning | `backend/tests/unit/test_cleaner.py` |
| Ingestion pipeline | `backend/tests/integration/test_ingest_pipeline.py` |
| No recommendation splitting | `backend/tests/integration/test_no_split_recommendations.py` |
| Dense/local embeddings | `backend/tests/unit/test_local_embedder.py`, `test_fallback_embedder.py` |
| BM25 | `backend/tests/unit/test_bm25.py` |
| Hybrid retrieval | `backend/tests/unit/test_hybrid.py`, `backend/tests/integration/test_hybrid_api.py` |
| Reranker | `backend/tests/unit/test_reranker.py` |
| Retrieval quality | `backend/tests/eval/test_retrieval_quality.py` |
| Citation extraction | `backend/tests/unit/test_citations.py` |
| Citation integrity | `backend/tests/unit/test_citation_integrity.py` |
| Grounding | `backend/tests/unit/test_grounding.py` |
| Grounding stress/adversarial | `backend/tests/unit/test_grounding_stress.py` |
| Scope guardrail | `backend/tests/unit/test_scope_guardrail.py`, `test_scope.py` |
| Clarification | `backend/tests/unit/test_clarification.py` |
| Greeting routing | `backend/tests/unit/test_greeting_guardrail.py` |
| Generation quality | `backend/tests/eval/test_generation_quality.py` |
| Generate API | `backend/tests/integration/test_generate_api.py` |
| Search API | `backend/tests/integration/test_hybrid_api.py` and search-related tests |
| Cache | `backend/tests/unit/test_caching.py` |
| Observability | `backend/tests/unit/test_observability.py` |
| Sentry | `backend/tests/unit/test_sentry_monitoring.py`, `test_sentry_spans.py`, `test_sentry_endpoint.py` |
| Performance/search latency | `backend/tests/integration/test_search_latency.py` |
| Configuration | `backend/tests/unit/test_config.py` |
| Graph | `backend/tests/unit/test_graph.py` |

---

# 7. Checklist Items That Need Special Attention

## 7.1 `schema/response_schema.json`

The Day 3 training material references a ready-made `schema/response_schema.json`.

**It is not present in the submitted project archive.**

The project instead implements structured responses through:

- `backend/app/models.py`
- `backend/app/generation/citations.py`
- `backend/app/generation/prompt.py`

If the evaluator explicitly checks for the literal file path `schema/response_schema.json`, add that artifact or confirm that the evaluator accepts the current Pydantic/API contract.

---

## 7.2 Formal Day 4 aggregate faithfulness metrics

The project has strong **claim-level validation**, but the primary `backend/app/evaluation.py` evaluator is a retrieval evaluator.

Therefore distinguish between:

- **implemented safety mechanism:** yes
- **dedicated aggregate unsupported-claim-rate metric/report:** not clearly implemented in the main evaluator

This distinction matters when writing the final project report.

---

## 7.3 Input risk classification architecture

The curriculum presents a conceptual risk-classification stage.

Eva AI implements this using deterministic guardrails and scope classification rather than a separate ML risk-classifier component.

Relevant locations:

- `backend/app/generation/guardrails.py`
- `backend/app/retrieval/scope.py`
- `backend/app/generation/clarification.py`

Functionally, the required decisions are represented, but architecturally the implementation is different.

---

# 8. End-to-End Checklist Trace

This is the shortest way to explain the project to a reviewer:

```text
Official PDF
    ↓
data/sources.yaml
    ↓
registry validation
    ↓
backend/app/ingestion/parser.py
    ↓
backend/app/ingestion/cleaner.py
    ↓
backend/app/ingestion/sectioner.py
    ↓
backend/app/ingestion/chunker.py
    ↓
backend/app/embeddings/*
    ↓
backend/app/retrieval/store.py
    ↓
ChromaDB index + metadata
    ↓
┌─────────────────────────────────────┐
│ Retrieval                            │
│ dense.py                             │
│ bm25.py                              │
│ hybrid.py                            │
│ reranker.py                          │
└─────────────────────────────────────┘
    ↓
backend/app/retrieval/scope.py
    ↓
backend/app/generation/guardrails.py
    ↓
backend/app/generation/assembler.py
    ↓
backend/app/generation/prompt.py
    ↓
LLM client
    ↓
backend/app/generation/citations.py
    ↓
claim-level grounding validation
    ↓
backend/app/api/generate.py
    ↓
frontend/components/AnswerCard.tsx
    +
frontend/components/chat/EvidencePanel.tsx
    ↓
User sees answer + traceable evidence
```

---

# 9. Reviewer-Friendly Requirement Matrix

| Checklist area | Implemented? | Primary file(s) | Tests / evidence |
|---|---|---|---|
| Official source | ✅ | `data/sources.yaml` | registry tests / ingestion |
| PDF parsing | ✅ | `ingestion/parser.py` | `test_ingest_pipeline.py` |
| Cleaning | ✅ | `ingestion/cleaner.py` | `test_cleaner.py` |
| Section-aware chunking | ✅ | `ingestion/sectioner.py`, `chunker.py` | `test_sectioner.py`, `test_chunker.py` |
| Embeddings | ✅ | `embeddings/*` | embedding tests |
| Vector DB | ✅ | `retrieval/store.py` | ingestion/integration tests |
| Dense retrieval | ✅ | `retrieval/dense.py` | retrieval tests |
| BM25 | ✅ | `retrieval/bm25.py` | `test_bm25.py` |
| Hybrid RRF | ✅ | `retrieval/hybrid.py` | `test_hybrid.py` |
| Reranking | ✅ | `retrieval/reranker.py` | `test_reranker.py` |
| Top-K tuning | ✅ | `config.py`, `evaluation.py` | retrieval evaluation |
| Precision@K | ✅ | `evaluation.py` | `test_retrieval_quality.py` |
| Golden retrieval set | ✅ | `tests/eval/golden_questions.yaml` | evaluation suite |
| Evidence panel | ✅ | `EvidencePanel.tsx` | UI implementation |
| Grounded prompt | ✅ | `generation/prompt.py` | grounding tests |
| Citation parsing | ✅ | `generation/citations.py` | citation tests |
| Claim-level citation enforcement | ✅ | `generation/citations.py` | grounding/citation tests |
| Prompt injection defense | ✅ | `generation/guardrails.py` | stress tests |
| Out-of-scope refusal | ✅ | `retrieval/scope.py` | scope tests |
| Insufficient-evidence refusal | ✅ | `citations.py`, `service.py` | grounding tests |
| Safe disclaimer | ✅ | `models.py`, API files | generation tests |
| Risk routing | ✅ / different architecture | `scope.py`, `guardrails.py`, `clarification.py` | scope/guardrail tests |
| Citation accuracy | ✅ | `citations.py` | citation integrity tests |
| Formal faithfulness metric | ⚠️ Partial | grounding validator + evaluation reports | verify evaluator expectation |
| Conversation history | ✅ | frontend chat/session files + `prompt.py` | generation integration tests |
| Response cache | ✅ | `retrieval/cache.py`, `generation/service.py` | `test_caching.py` |
| SSE streaming | ✅ | `api/generate.py`, frontend streaming hook | generate integration tests |
| Graph expansion | ✅ | `graph.py`, `generation/service.py` | graph tests |
| Sentry | ✅ | `monitoring/sentry.py`, frontend Sentry config | Sentry tests |
| PHI-safe logging | ✅ | monitoring/config | observability tests |
| Rate limiting | ✅ | `ratelimit.py` | `ratelimit_test.py` |

---

# 10. What to Say in the Demo

If a judge asks **“Where is this checklist item implemented?”**, use this pattern:

> **Requirement → production file → supporting test → UI evidence (if applicable).**

Examples:

### “Where is grounding implemented?”

```text
backend/app/generation/prompt.py
backend/app/generation/assembler.py
backend/app/generation/citations.py
backend/tests/unit/test_grounding.py
backend/tests/unit/test_grounding_stress.py
```

### “Where is retrieval quality measured?”

```text
backend/app/evaluation.py
backend/tests/eval/golden_questions.yaml
backend/tests/eval/test_retrieval_quality.py
DAY2_RETRIEVAL_OPTIMIZATION.md
```

### “Where are citations shown?”

```text
backend/app/generation/citations.py
frontend/components/AnswerCard.tsx
frontend/components/chat/EvidencePanel.tsx
```

### “Where is refusal implemented?”

```text
backend/app/retrieval/scope.py
backend/app/generation/guardrails.py
backend/app/generation/citations.py
backend/app/generation/service.py
backend/app/api/generate.py
```

### “Where is the evidence trace shown to the judge?”

```text
frontend/components/chat/EvidencePanel.tsx
frontend/components/AnswerCard.tsx
```

---

# 11. Final Audit Conclusion

The project has a **complete end-to-end implementation** for the major Day 1–4 RAG requirements:

```text
Source
→ Ingestion
→ Section-aware Chunking
→ Embeddings
→ Vector Index
→ Dense/BM25/Hybrid Retrieval
→ Retrieval Evaluation
→ Scope Guardrails
→ Grounded Generation
→ Citation Resolution
→ Claim-level Grounding Validation
→ Refusal / Abstention
→ Evidence Inspector UI
```

The two items that should **not** be described as literal one-to-one matches with the training slides without qualification are:

1. `schema/response_schema.json` — the referenced file is not present; the project uses Pydantic/API contracts instead.
2. Formal aggregate Day 4 faithfulness/unsupported-claim-rate metrics — the project has strong claim-level validation, but the main evaluator is primarily retrieval-focused.

Everything else in the main Day 1–4 checklist has a clear implementation location in the repository, with most major components backed by dedicated unit/integration/evaluation tests.
