# Clinical Decision Support Lite — Constitution

Governing principles for the AI Clinical Decision Support Lite hackathon project.
These rules bind every specification, plan, task, and line of code in this repository.

## Core Principles

### I. Evidence-Grounded Answers Only (NON-NEGOTIABLE)

The system answers **exclusively** from text retrieved out of the ingested guideline
corpus. Model parametric memory is never a permitted source of clinical content.

- If retrieval returns no chunk above the configured relevance floor, the system MUST
  respond that it cannot find supporting evidence. It MUST NOT produce a clinical
  statement anyway.
- A fluent answer is not a safe answer. Fluency is never accepted as evidence of
  correctness.
- Every clinical claim in an answer traces to at least one retrieved chunk.

*Rationale: the entire premise of the project is that clinical guidance must be
traceable to official evidence. A confident guess is the specific failure mode this
system exists to prevent.*

### II. Citation Metadata Is Structural, Not Cosmetic (NON-NEGOTIABLE)

Every chunk carries, at minimum: `document_name`, `page_number`, `section_title`,
`chunk_id`, `source_url`, `text`.

- Metadata MUST be stored **with** the vector entry in the vector store. Storing it in
  a parallel spreadsheet, sidecar JSON, or any structure that can drift out of sync is
  forbidden.
- Retrieval MUST return metadata and relevance score alongside text in a single call.
- Any chunk must be traceable by a human back to the exact page of the source PDF.

*Rationale: a citation the system cannot substantiate is worse than no citation — it
manufactures false trust.*

### III. Source Legitimacy and Provenance

Only official, public, legally usable documents enter the corpus.

- Permitted: published clinical guidelines and public health documents from recognised
  bodies (NICE, WHO, CDC, USPSTF and equivalents).
- Forbidden: hospital records, patient records, PHI or any identifiable health data,
  credential-gated datasets.
- Every source MUST be registered with its publisher, publication year, retrieval URL,
  document type, and a written justification of why it is credible and public.
- Sources whose type is not `guideline`, and sources older than 10 years, MUST be
  flagged as such in metadata and surfaced visibly wherever their chunks appear.

*Rationale: provenance that is not recorded at ingestion time cannot be reconstructed
later, and evidence quality varies enormously between a current guideline and an old
bulletin.*

### IV. Narrow Scope Discipline

The system serves one clinical topic at a time, declared in a one-sentence scope
statement before implementation begins.

- Out of scope by construction: patient-specific diagnosis, emergency medical advice,
  general "all diseases" assistance, and cross-specialty expansion.
- Every user-facing response carries a disclaimer that the system is a decision-support
  aid for qualified users, not a diagnostic or emergency service.

*Rationale: a narrow corpus can actually be evaluated. A broad one can only be
demonstrated.*

### V. Staged Delivery — Retrieval Before Generation

Foundation quality gates the layers above it.

- Ingestion, chunking, metadata, and indexing are completed and verified before any
  generation work begins.
- Prompt engineering and UI polish are forbidden until retrieval demonstrably returns
  reasonable evidence for the evaluation question set.
- Architectural seams for later stages may be defined; their implementations may not
  jump the queue.

*Rationale: every downstream quality score is bounded by the quality of the retrieved
chunks. Optimising generation over a bad index is wasted effort.*

### VI. Human Verification Over Automated Confidence

Similarity scores are signals, not proof.

- A human MUST read a sample of chunks and confirm each is coherent standalone.
- A human MUST trace at least one chunk back to its source PDF page.
- Weak and low-scoring results MUST remain visible in tooling, never silently filtered,
  so failure modes stay observable.

*Rationale: retrieval systems fail quietly. Only inspection surfaces the failure.*

## Operating Constraints

- **Stack**: Python/FastAPI backend, Next.js frontend, single repository, monolithic
  deployment. ChromaDB embedded as the vector store. OpenRouter as the single model
  provider for both embeddings and generation.
- **Reproducibility**: the corpus and the index rebuild deterministically from files
  committed to the repository plus one documented command.
- **Configuration**: model identifiers, chunk sizing, and retrieval depth are
  configuration values, never hard-coded literals scattered through modules.
- **Secrets**: API keys live only in `.env`, never committed.

## Development Workflow

- Specifications precede plans; plans precede tasks; tasks precede code.
- Retrieval quality changes MUST be validated against the golden question set before
  being accepted.
- Any deviation from a principle above MUST be recorded explicitly as an accepted risk
  with its mitigation, in the plan's Complexity Tracking section.

## Governance

This constitution supersedes competing preferences, including expedience under time
pressure. Amendments require an explicit entry in the Sync Impact Report below, a
version bump, and propagation to dependent artifacts.

Compliance is verified at two points: the Constitution Check gates in `plan.md`, and
the end-of-day review gates in the feature specification.

**Version**: 1.0.0 | **Ratified**: 2026-08-16 | **Last Amended**: 2026-08-16

<!--
Sync Impact Report
==================
Version change: [TEMPLATE] -> 1.0.0
Rationale: Initial ratification. Principles derived from the Day 1 hackathon brief
("AI Clinical Decision Support Lite") and the architecture decisions confirmed with
the project owner on 2026-08-16.

Principles defined:
  I.   Evidence-Grounded Answers Only (NON-NEGOTIABLE)
  II.  Citation Metadata Is Structural, Not Cosmetic (NON-NEGOTIABLE)
  III. Source Legitimacy and Provenance
  IV.  Narrow Scope Discipline
  V.   Staged Delivery - Retrieval Before Generation
  VI.  Human Verification Over Automated Confidence

Sections added: Operating Constraints, Development Workflow, Governance

Templates requiring updates:
  .specify/templates/plan-template.md      - OK (Constitution Check gate is generic)
  .specify/templates/spec-template.md      - OK (no principle-specific edits needed)
  .specify/templates/tasks-template.md     - OK (no principle-specific edits needed)
  .specify/templates/checklist-template.md - OK (no principle-specific edits needed)

Follow-up TODOs:
  - None. An earlier proposal to retain "WHO Drug Information Vol 17 No.4 (2003)" (a
    periodical, not a guideline) was withdrawn by the project owner on 2026-08-16. The
    corpus is single-source (NICE NG243), so Principle III holds with no exceptions.
    The document_type / publication_year flagging mandated by Principle III remains in
    force as a standing safeguard for any future source addition.
-->
