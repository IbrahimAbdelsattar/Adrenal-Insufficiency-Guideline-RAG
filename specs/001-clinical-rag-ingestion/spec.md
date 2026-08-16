# Feature Specification: Clinical Guideline Ingestion & Retrieval Baseline

**Feature Branch**: `001-clinical-rag-ingestion`

**Created**: 2026-08-16

**Status**: Draft

**Input**: Day 1 of the AI Clinical Decision Support Lite hackathon — research, scope, and document ingestion. Build the monolithic architecture (FastAPI + Next.js) and implement the ingestion pipeline through a working first vector index with a retrieval inspector.

## Scope Statement

> This system helps **clinicians and clinical trainees** answer questions about
> **adrenal insufficiency identification and management** using **NICE guideline NG243
> and registered supporting official sources**.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest a guideline corpus into a searchable index (Priority: P1)

A team member places official guideline PDFs into the corpus directory, registers each
one with its provenance, and runs a single command. The command parses every PDF,
cleans extraction noise, splits the text into section-aware chunks, attaches full
citation metadata to each chunk, embeds them, and writes them to a persistent vector
index.

**Why this priority**: Nothing else in the product can exist without it. This is the
entire Day 1 deliverable and every later quality score is bounded by it.

**Independent Test**: Run the ingest command against the corpus and confirm the vector
store reports a non-zero chunk count, with every chunk carrying complete metadata.

**Acceptance Scenarios**:

1. **Given** a registered PDF in the corpus directory, **When** the ingest command is
   run, **Then** the index contains chunks from that document and reports the count per
   document.
2. **Given** a document with repeated page headers and footers, **When** it is parsed,
   **Then** those repeated lines are absent from chunk text.
3. **Given** a NICE guideline with numbered recommendations, **When** it is chunked,
   **Then** no single numbered recommendation is split across two chunks.
4. **Given** any chunk in the index, **When** it is retrieved, **Then** it carries
   `document_name`, `page_number`, `section_title`, `chunk_id`, `source_url`,
   `document_type`, and `publication_year`.
5. **Given** the ingest command is run twice, **When** the second run completes,
   **Then** the index is rebuilt deterministically without duplicate chunks.

---

### User Story 2 - Inspect retrieval results for a clinical question (Priority: P1)

A team member types a clinical question into the web interface and sees the top-ranked
chunks returned as cards, each showing its relevance score, source document, page
number, section title, and full text — enough to judge whether the retrieved evidence
actually answers the question.

**Why this priority**: This is the literal end-of-day demo requirement — question → top
chunks → source page and section. It is also the only way to debug retrieval quality.

**Independent Test**: Submit a question through the UI and confirm ranked chunks appear
with complete, correct provenance on each card.

**Acceptance Scenarios**:

1. **Given** a populated index, **When** a user submits a clinical question, **Then**
   the top-K chunks are displayed ranked by relevance score.
2. **Given** a returned chunk, **When** the user reads its card, **Then** document name,
   page number, and section title are all visible.
3. **Given** a chunk sourced from a non-guideline or dated document, **When** it is
   displayed, **Then** its document type and publication year are visibly flagged.
4. **Given** a question with no good match, **When** results return, **Then** low-scoring
   results remain visible with their scores rather than being silently hidden.
5. **Given** an empty index, **When** a question is submitted, **Then** the interface
   states that no evidence is available rather than failing silently.

---

### User Story 3 - Verify retrieval quality against a golden question set (Priority: P2)

A team member runs the evaluation suite. It executes a fixed set of clinical questions
with known correct source sections and reports, per question, whether the expected
section appeared in the top-K results, plus an overall hit rate.

**Why this priority**: Converts the brief's "run 5–10 clinical questions" gate into a
repeatable regression test, so Day 2 retrieval tuning can be measured rather than
guessed at.

**Independent Test**: Run the evaluation command and confirm it emits a per-question
pass/fail table and an aggregate hit-rate figure.

**Acceptance Scenarios**:

1. **Given** the golden question set, **When** evaluation runs, **Then** each question
   reports whether its expected section was retrieved within top-K.
2. **Given** a completed run, **When** results are summarised, **Then** an overall
   hit-rate percentage is reported.
3. **Given** a chunking or embedding configuration change, **When** evaluation is re-run,
   **Then** the hit rate is directly comparable to the previous run.

---

### User Story 4 - Confirm source provenance and credibility (Priority: P3)

A reviewer opens the source registry and sees, for every document in the corpus, its
publisher, publication year, retrieval URL, document type, and a written justification
of why it is credible and legally usable.

**Why this priority**: Required by the end-of-day review gates and by the constitution's
provenance principle, but it does not block the pipeline from functioning.

**Independent Test**: Read the registry file and confirm every corpus PDF has a complete,
non-placeholder entry.

**Acceptance Scenarios**:

1. **Given** a PDF in the corpus directory, **When** the registry is checked, **Then** a
   complete entry exists for it.
2. **Given** a PDF with no registry entry, **When** ingestion runs, **Then** ingestion
   fails with a clear error naming the unregistered file.

---

### Edge Cases

- A PDF whose text layer is missing or scanned as images — ingestion must report this
  clearly rather than indexing empty chunks.
- Multi-column or table-heavy pages where extraction order scrambles text.
- Front matter (cover, rights notice, contents page with dot leaders) that carries no
  clinical content and must be excluded.
- A recommendation longer than the maximum chunk size, which must not be silently
  truncated.
- Non-ASCII glyph corruption from bullet characters in the source PDF.
- A question in scope for the corpus topic but with genuinely no matching guidance.
- A question entirely outside the declared clinical scope.

## Requirements *(mandatory)*

### Functional Requirements

**Corpus and provenance**

- **FR-001**: System MUST maintain a source registry recording, per document: display
  name, publisher, publication year, retrieval URL, document type, and a credibility
  justification.
- **FR-002**: System MUST refuse to ingest any PDF absent from the source registry.
- **FR-003**: System MUST classify each source by document type and mark any source that
  is not a current clinical guideline as requiring visible caution.

**Parsing and cleaning**

- **FR-004**: System MUST extract text from each PDF while preserving the true source
  page number for every extracted span.
- **FR-005**: System MUST remove repeated page headers and footers, page-number
  artefacts, and rights notices from extracted text.
- **FR-006**: System MUST repair broken line breaks and hyphenated word splits
  introduced by extraction.
- **FR-007**: System MUST normalise corrupted glyphs, including bullet characters, into
  clean text.
- **FR-008**: System MUST exclude front matter and contents listings from the indexed
  content.
- **FR-009**: System MUST report, per document, the page count processed and the count
  of pages yielding no usable text.

**Chunking**

- **FR-010**: System MUST detect the document's section hierarchy and associate each
  chunk with its section title.
- **FR-011**: System MUST treat each numbered clinical recommendation as an atomic unit
  that is never split across chunks.
- **FR-012**: System MUST produce chunks within a configurable target size band,
  defaulting to 400–800 tokens.
- **FR-013**: System MUST ensure each chunk is comprehensible standalone, without
  requiring the surrounding document.
- **FR-014**: System MUST emit a chunk exceeding the maximum size, rather than truncating
  it, when an atomic recommendation is itself oversized, and MUST flag that chunk.

**Metadata and indexing**

- **FR-015**: System MUST attach to every chunk: `document_name`, `page_number`,
  `section_title`, `chunk_id`, `source_url`, `document_type`, `publication_year`, and
  `text`.
- **FR-016**: System MUST assign each chunk a stable, human-readable identifier that
  encodes its document and page.
- **FR-017**: System MUST store metadata within the vector store entry itself, not in any
  separate file.
- **FR-018**: System MUST persist the index to disk so it survives process restart.
- **FR-019**: System MUST record the embedding model identifier and configuration used to
  build the index.
- **FR-020**: System MUST rebuild the index deterministically and idempotently.

**Retrieval**

- **FR-021**: System MUST accept a natural-language clinical question and return the
  top-K most relevant chunks, K being configurable.
- **FR-022**: System MUST return each result's relevance score together with its full
  metadata and text in a single response.
- **FR-023**: System MUST return low-scoring results with their scores rather than
  discarding them.
- **FR-024**: System MUST expose retrieval through both an HTTP endpoint and a
  command-line interface.
- **FR-025**: System MUST indicate explicitly when no chunk meets the relevance floor.

**Interface**

- **FR-026**: Users MUST be able to submit a clinical question through a web interface
  and view ranked results.
- **FR-027**: Interface MUST display, per result: relevance score, document name, page
  number, section title, and full chunk text.
- **FR-028**: Interface MUST visibly flag results originating from non-guideline or dated
  sources.
- **FR-029**: Interface MUST display a disclaimer stating the system is a decision-support
  aid, not a diagnostic or emergency service.
- **FR-030**: Interface MUST report index health, including document and chunk counts.

**Evaluation**

- **FR-031**: System MUST maintain a golden set of at least 10 clinical questions, each
  with its expected source section.
- **FR-032**: System MUST report per-question retrieval success and an aggregate hit rate.
- **FR-033**: Evaluation MUST be runnable as an automated test.

**Architectural seams (defined, not implemented in this feature)**

- **FR-034**: System MUST define the answer-generation interface contract without
  implementing it, so generation can be added without restructuring.
- **FR-035**: System MUST define the retriever as a replaceable interface so hybrid or
  reranked strategies can substitute in without changes to the API layer.

### Key Entities

- **Source Document**: a registered guideline PDF. Carries display name, publisher,
  publication year, retrieval URL, document type, credibility justification, and local
  file path.
- **Chunk**: an indexed unit of guideline text. Carries stable identifier, text, page
  number, section title, recommendation label where present, oversize flag, and a
  reference to its source document.
- **Retrieval Result**: a chunk paired with a relevance score for a specific query.
- **Golden Question**: an evaluation question paired with its expected source document
  and section.
- **Index Manifest**: a record of how the current index was built — embedding model,
  chunking configuration, document and chunk counts, build timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A team member can go from raw PDFs to a queryable index with a single
  documented command, in under 10 minutes on a normal laptop.
- **SC-002**: 100% of indexed chunks carry complete, non-empty citation metadata.
- **SC-003**: For at least 8 of the 10 golden questions, the expected source section
  appears within the top 5 retrieved chunks.
- **SC-004**: A reviewer can select any displayed chunk and locate its exact text on the
  stated page of the original PDF.
- **SC-005**: Of 5 randomly sampled chunks, all 5 are judged coherent and standalone by a
  human reader.
- **SC-006**: Zero numbered recommendations are split across chunk boundaries in the
  indexed corpus.
- **SC-007**: A question submitted through the interface returns ranked, fully attributed
  results in under 3 seconds.
- **SC-008**: Every corpus document has a complete provenance registry entry.
- **SC-009**: A new team member can start both services and reach a working interface by
  following the quickstart, without assistance.

## End-of-Day Review Gates

Derived directly from the hackathon brief. All must pass to proceed to Day 2.

**Source readiness**
- [ ] All PDFs are official and public
- [ ] Scope is narrow and stated in one sentence
- [ ] Source URLs and names are recorded
- [ ] Licensing concerns are addressed

**Chunk readiness**
- [ ] Chunks are readable standalone
- [ ] Chunks preserve page number and section title
- [ ] Recommendations are split correctly
- [ ] Extraction noise is removed

**Search readiness**
- [ ] Embeddings are created and the model is documented
- [ ] Metadata is returned with retrieved chunks
- [ ] 10 golden questions retrieve reasonable evidence
- [ ] Weak results remain visible

**Demo gate**
- [ ] The team can show: question → top chunks → source page and section

## Assumptions

- The corpus is fixed for this feature; live document upload is out of scope.
- The system is used by qualified clinical users, not patients.
- No authentication or multi-user support is required at this stage.
- No answer generation occurs in this feature; retrieval output is the deliverable.
- Documents have an extractable text layer; OCR is out of scope.
- English-language sources only.
- A single model provider serves both embeddings and later generation.

## Out of Scope

- Answer generation, prompt engineering, and safety-filtering of generated text
- Hybrid search, reranking, and query expansion
- Live PDF upload through the interface
- Authentication, user accounts, conversation history
- OCR for scanned documents
- Any clinical topic beyond the declared scope statement
