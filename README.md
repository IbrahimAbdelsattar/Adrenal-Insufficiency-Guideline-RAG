# Sapphire VEIL — Clinical Decision Support (Adrenal Insufficiency RAG)

[![Python Version](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Node Version](https://img.shields.io/badge/node-24.x-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15.x-black.svg)](https://nextjs.org/)
[![ChromaDB](https://img.shields.io/badge/VectorStore-ChromaDB-orange.svg)](https://www.trychroma.com/)
[![OpenRouter](https://img.shields.io/badge/Embeddings-OpenRouter_1536--dim-purple.svg)](https://openrouter.ai/)
[![License](https://img.shields.io/badge/License-NICE_Notice_of_Rights-red.svg)](https://www.nice.org.uk/terms-and-conditions#notice-of-rights)

---

## 📌 Executive Summary & Clinical Scope

**Sapphire VEIL (Clinical Decision Support Lite)** is an evidence-grounded Retrieval-Augmented Generation (RAG) platform designed to assist **clinicians, general practitioners, and clinical trainees** in making informed clinical decisions regarding **adrenal insufficiency identification, diagnosis, emergency crisis management, and sick-day dosing rules**.

> **Scope Statement**:
> *"This system helps clinicians and clinical trainees answer questions about **adrenal insufficiency identification and management** using **NICE guideline NG243** and registered supporting official sources."*

The application pairs a high-performance **FastAPI backend** with a **Next.js 15 Monomorphic Retrieval Inspector** frontend. It ingests official clinical guidelines, strips extraction noise while preserving page fidelity and section context, packs atomic clinical recommendations into token-budgeted chunks, embeds them using OpenRouter (`openai/text-embedding-3-small` / `gemini-embedding-001`), and exposes a transparent, interactive retrieval inspector with full bilingual (English & Arabic) support.

---

## 📜 Guiding Principles (System Constitution)

The core architecture enforces six strict constitutional principles:

1. **Evidence-Grounded Answers Only**: No generation or answer synthesis path exists that can bypass retrieval. Answers must be strictly grounded in verified evidence.
2. **Citation Metadata Is Structural**: Citation metadata (`document_name`, `page_number`, `section_title`, `source_url`, `chunk_id`) is stored natively on every vector entry and returned alongside relevance scores in a single query call—never in an external sidecar file.
3. **Source Legitimacy and Provenance**: Every corpus document MUST be registered in [data/sources.yaml](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/sources.yaml) with its publisher, publication year, source URL, document type, and written credibility justification. Ingestion fails closed on unregistered files.
4. **Narrow Scope Discipline**: Restricted strictly to adrenal insufficiency identification and management based on NICE NG243. Prominent decision-support disclaimers are enforced across UI and API responses.
5. **Staged Delivery**: Retrieval quality is fully verified, measured, and benchmarked before any LLM answer generation is introduced. `POST /api/generate` returns `501 Not Implemented` by design.
6. **Human Verification Over Automated Confidence**: Weak or low-scoring evidence is never hidden or silently filtered; every retrieved chunk provides exact page-number trace-back to the original source PDF.

---

## 🏗️ System Architecture & Component Topology

The system is structured as a **monolithic repository** with strict internal modularity and protocol-driven replacement seams:

- **Development**: Two concurrent processes (`FastAPI` on `:8000` and `Next.js` on `:3000` with dev rewrites for `/api/*`).
- **Production**: Single deployable process where FastAPI serves the static frontend export (`frontend/out`).
- **Storage**: Persistent embedded **ChromaDB** vector store at [data/index/](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/index) paired with a self-describing [manifest.json](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/index/manifest.json).

### High-Level Component Topology

```mermaid
graph TD
    subgraph ClientLayer["Frontend (Next.js 15 / React 19)"]
        UI["Retrieval Inspector UI (app/page.tsx)"]
        SearchComp["SearchBox Component"]
        CardComp["ChunkCard Component"]
        StatusComp["IndexStatus Component"]
        LangToggle["LanguageToggle (EN / العربية)"]
        ThemeToggle["ThemeToggle (Light / Dark)"]
        ApiClient["API Client (frontend/lib/api.ts)"]
    end

    subgraph ServerLayer["Backend (FastAPI Monolith)"]
        AppMain["FastAPI App Entry (backend/app/main.py)"]
        SearchApi["Search & Health API (api/search.py)"]
        GenStub["Generate API 501 Stub (api/generate.py)"]
        CliApp["CLI Interface (cli.py)"]
        
        subgraph PipelineLayer["Ingestion Pipeline"]
            Reg["Source Registry (ingestion/registry.py)"]
            Parser["PyMuPDF Parser (ingestion/parser.py)"]
            Cleaner["Boilerplate Cleaner (ingestion/cleaner.py)"]
            Sectioner["Sectioner (ingestion/sectioner.py)"]
            Chunker["Atomic Recommendation Chunker (ingestion/chunker.py)"]
            Pipeline["Pipeline Orchestrator (ingestion/pipeline.py)"]
        end
        
        subgraph AbstractionSeams["Protocol Seams"]
            RetrieverProto["Retriever Protocol (retrieval/base.py)"]
            EmbedderProto["Embedder Protocol (embeddings/base.py)"]
        end

        DenseRetriever["Dense Cosine Retriever (retrieval/dense.py)"]
        OpenRouterEmbed["OpenRouter Embedding Client (embeddings/openrouter.py)"]
    end

    subgraph StorageLayer["Data & Persistence"]
        Corpus["Registered PDFs (data/corpus/)"]
        SourcesYaml["Source Registry (data/sources.yaml)"]
        ChromaDB[("ChromaDB Vector Store (data/index/)")]
        Manifest["Index Manifest (data/index/manifest.json)"]
    end

    subgraph ExternalProvider["External APIs"]
        OpenRouter["OpenRouter / OmniRoute Gateway API"]
    end

    %% Client Interactions
    UI --> SearchComp
    UI --> CardComp
    UI --> StatusComp
    UI --> LangToggle
    UI --> ThemeToggle
    SearchComp --> ApiClient
    ApiClient -->|"HTTP /api/search"| SearchApi
    StatusComp -->|"HTTP /api/index"| SearchApi

    %% Server Internal Routing
    AppMain --> SearchApi
    AppMain --> GenStub
    SearchApi --> RetrieverProto
    RetrieverProto -.-> DenseRetriever
    DenseRetriever --> EmbedderProto
    EmbedderProto -.-> OpenRouterEmbed
    OpenRouterEmbed -->|"POST /api/v1/embeddings"| OpenRouter
    DenseRetriever --> ChromaDB

    %% CLI and Pipeline Connections
    CliApp --> Pipeline
    CliApp --> DenseRetriever
    Pipeline --> Reg
    Pipeline --> Parser
    Pipeline --> Cleaner
    Pipeline --> Sectioner
    Pipeline --> Chunker
    Pipeline --> EmbedderProto
    Pipeline --> ChromaDB
    Pipeline --> Manifest

    %% Data Inputs
    Reg --> SourcesYaml
    Parser --> Corpus
```

---

## 🔬 RAG Ingestion Pipeline & Chunking Mechanics

The RAG pipeline translates multi-page clinical guideline PDFs into section-aware, citation-ready vector entries without losing clinical context.

### Ingestion Flow Diagram

```mermaid
graph LR
    subgraph Input["Input Data"]
        PDF["PDF File (NG243 Guideline)"]
        YAML["sources.yaml Registry"]
    end

    subgraph Stage1["1. Validation & Extraction"]
        VCheck["Fail-Closed Registry Check"]
        PyMuPDF["PyMuPDF Span Extraction (font size/weight, page #)"]
    end

    subgraph Stage2["2. Cleaning & Structure"]
        Boilerplate["Boilerplate Removal (>60% ratio)"]
        Glyph["Glyph & Hyphenation Repair"]
        FrontMatter["Front-Matter Exclusion"]
        SectionDetect["Section Hierarchy Detection (1.1 / 1.1.1)"]
    end

    subgraph Stage3["3. Atomic Chunking"]
        RecAtom["Atomic Recommendation Preservation"]
        TokenBudget["Tiktoken Budget Packing (400-800 tok)"]
        OversizedFlag["Oversized Chunk Flagging"]
    end

    subgraph Stage4["4. Embedding & Indexing"]
        OpenRouterEmbed["Batch Embedding (1536-dim)"]
        ChromaStore["ChromaDB Vector Storage (Scalar Metadata)"]
        ManifestGen["Manifest Generation (manifest.json)"]
    end

    PDF --> VCheck
    YAML --> VCheck
    VCheck --> PyMuPDF
    PyMuPDF --> Boilerplate
    Boilerplate --> Glyph
    Glyph --> FrontMatter
    FrontMatter --> SectionDetect
    SectionDetect --> RecAtom
    RecAtom --> TokenBudget
    TokenBudget --> OversizedFlag
    OversizedFlag --> OpenRouterEmbed
    OpenRouterEmbed --> ChromaStore
    ChromaStore --> ManifestGen
```

### Pipeline Key Transformations

1. **Fail-Closed Registry Validation** ([ingestion/registry.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/ingestion/registry.py)): Verifies every PDF in `data/corpus/` against [data/sources.yaml](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/sources.yaml). Unregistered PDFs immediately abort ingestion (Exit code 1).
2. **Page-Faithful Parsing** ([ingestion/parser.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/ingestion/parser.py)): PyMuPDF (`fitz`) extracts text spans with font size, weight, and 1-indexed source PDF page numbers.
3. **Frequency-Based Cleaning** ([ingestion/cleaner.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/ingestion/cleaner.py)): Detects lines appearing on >60% of pages (footers, rights notices) and removes them dynamically. Repairs hyphenated word splits (`\w+-\n\w+`) and normalizes bullet glyphs (`•` $\rightarrow$ `-`). Filters non-clinical front matter (cover, contents, dot leaders).
4. **Hierarchy Detection** ([ingestion/sectioner.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/ingestion/sectioner.py)): Identifies `N.N` major section headings (e.g., `1.2 Initial identification and referral`) and `N.N.N` numbered recommendations (e.g., `1.2.1`).
5. **Atomic Recommendation Packing** ([ingestion/chunker.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/ingestion/chunker.py)): Numbered recommendations are **atomic**—they are never split across chunks. Consecutive sibling recommendations under the same section heading are packed into token budgets targetting 400–800 tokens (`tiktoken` `cl100k_base`). Oversized atomic recommendations are emitted whole and flagged (`is_oversized=true`).
6. **Batched Embeddings** ([embeddings/openrouter.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/embeddings/openrouter.py)): Requests 1536-dimensional vector embeddings via OpenRouter's OpenAI-compatible endpoint with exponential backoff retries.
7. **Atomic Collection Swap** ([retrieval/store.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/retrieval/store.py)): Reads/writes ChromaDB. If ingestion succeeds, the index collection is atomically swapped; if ingestion fails, existing index state is preserved.

---

## 👥 System Use Cases & User Roles

```mermaid
graph LR
    subgraph Actors["Users & System Roles"]
        Clinician["Clinician / Trainee"]
        Admin["Technical Admin"]
        Evaluator["Quality Evaluator"]
    end

    subgraph SystemBoundary["Sapphire VEIL Clinical Decision Support System"]
        UC1["Query Adrenal Insufficiency Guidance"]
        UC2["Inspect Retrieved Evidence & Source Attribution"]
        UC3["Toggle Bilingual English / Arabic Layout"]
        UC4["Toggle Monomorphic Light / Dark Mode"]
        UC5["Ingest Guideline Corpus (CLI)"]
        UC6["Validate Source Provenance & Registry"]
        UC7["Run Golden Question Evaluation Suite"]
        UC8["Monitor Index Health & Metadata"]
    end

    Clinician --> UC1
    Clinician --> UC2
    Clinician --> UC3
    Clinician --> UC4

    Admin --> UC5
    Admin --> UC6
    Admin --> UC8

    Evaluator --> UC7
    Evaluator --> UC2
```

### Detailed User Stories

| Story ID | Priority | User Role | Scenario & Goal | Acceptance Criteria |
|---|---|---|---|---|
| **US1** | P1 | Technical Admin | Ingest guideline PDFs into a vector store via a single CLI command. | Non-zero chunk count; 100% metadata completeness; atomic recommendations preserved without splits. |
| **US2** | P2 | Clinician / Trainee | Search clinical questions and inspect ranked chunk cards with full provenance. | Top-K chunks returned with score, page, section, text; weak results stay visible; disclaimer displayed. |
| **US3** | P2 | Quality Evaluator | Benchmark retrieval performance against a golden question set. | Per-question HIT/MISS report; aggregate hit-rate calculated against 80% target depth. |
| **US4** | P3 | Reviewer | Verify legitimacy, licensing, and credibility of source guidelines. | [data/sources.yaml](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/sources.yaml) holds publisher, year, URL, and credibility justification for every corpus PDF. |

---

## 🔄 Interaction & Execution Flow Diagrams

### 1. Clinical Question Retrieval Flow (Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    actor User as Clinician / User
    participant UI as Next.js Inspector UI
    participant API as FastAPI Backend (/api/search)
    participant Ret as Dense Retriever
    participant Emb as OpenRouter Embedder
    participant OR as OpenRouter / OmniRoute API
    participant VStore as ChromaDB Store

    User->>UI: Submit question ("What are the symptoms of adrenal insufficiency?")
    UI->>API: POST /api/search { query, top_k: 5 }
    API->>Ret: search(query="...", top_k=5)
    Ret->>Emb: embed_query(query)
    Emb->>OR: POST /api/v1/embeddings { input: query, model: "..." }
    OR-->>Emb: 1536-dim vector embedding
    Emb-->>Ret: Vector array
    Ret->>VStore: query(query_embeddings, n_results=5)
    VStore-->>Ret: Top-5 chunks + distances + scalar metadatas
    Ret->>Ret: Calculate scores (1 - distance) & set below_floor flag
    Ret-->>API: List of RetrievalResult objects
    API-->>UI: SearchResponse (JSON with evidence_found, results, latency_ms)
    UI-->>User: Render ranked ChunkCards with score gauge, document, page, section & text
```

### 2. Ingestion Command Execution (Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    actor Admin as System Administrator
    participant CLI as CLI App (python -m backend.app.cli)
    participant Reg as Source Registry
    participant Parse as PyMuPDF Parser
    participant Clean as Cleaner & Sectioner
    participant Chunk as Atomic Chunker
    participant Emb as OpenRouter Embedder
    participant VStore as ChromaDB Vector Store

    Admin->>CLI: python -m backend.app.cli ingest
    CLI->>Reg: validate_corpus(corpus_dir, sources_yaml)
    Reg-->>CLI: Confirmed registered PDF (NICE NG243)
    CLI->>Parse: parse_pdf("adrenal-insufficiency-....pdf")
    Parse-->>CLI: Spans with page numbers & font metadata
    CLI->>Clean: clean_spans() & detect_sections()
    Clean-->>CLI: Cleaned spans + Section hierarchy (1.1, 1.1.1)
    CLI->>Chunk: pack_chunks(sections, token_budget=400-800)
    Chunk-->>CLI: Atomic recommendation chunks
    CLI->>Emb: embed_documents(chunk_texts)
    Emb->>Emb: Batch requests (size 100) to Gateway API
    Emb-->>CLI: Vector embeddings list
    CLI->>VStore: atomic_swap_collection(chunks, embeddings)
    VStore-->>CLI: Collection updated & manifest.json saved
    CLI-->>Admin: OK: Document indexed successfully
```

### 3. Document Lifecycle & Validation (Activity Diagram)

```mermaid
stateDiagram-v2
    [*] --> CheckRegistration: Start Ingestion Command
    
    state CheckRegistration {
        [*] --> LoadSourcesYaml
        LoadSourcesYaml --> ValidatePDFsInCorpus
        ValidatePDFsInCorpus --> FailUnregistered: PDF not in sources.yaml
        ValidatePDFsInCorpus --> PassRegistry: All PDFs registered
    }

    FailUnregistered --> [*]: Abort with Exit Code 1

    state PassRegistry {
        [*] --> ExtractPyMuPDF
        ExtractPyMuPDF --> CheckTextLayer
        CheckTextLayer --> FailScanned: No text layer
        CheckTextLayer --> ProcessPages: Spans extracted
    }

    FailScanned --> [*]: Abort with Exit Code 2

    state ProcessPages {
        [*] --> BoilerplateCleaning
        BoilerplateCleaning --> GlyphNormalisation
        GlyphNormalisation --> FrontMatterFilter
        FrontMatterFilter --> SectionHierarchyDetection
    }

    state ChunkingAndEmbedding {
        SectionHierarchyDetection --> AtomicRecommendationPacking
        AtomicRecommendationPacking --> CheckChunkSize
        CheckChunkSize --> EmitNormalChunk: 400 <= tokens <= 800
        CheckChunkSize --> EmitOversizedChunk: tokens > 800 (Atomic Rec)
        EmitNormalChunk --> BatchEmbedding
        EmitOversizedChunk --> BatchEmbedding
        BatchEmbedding --> OpenRouterAPI
        OpenRouterAPI --> VectorPersistence
    }

    VectorPersistence --> WriteManifest: Persist to data/index/
    WriteManifest --> [*]: Success (Exit Code 0)
```

---

## 🎨 Sapphire VEIL Visual System & Internationalization

The user interface implements the **Sapphire VEIL Design System**, engineered specifically for high visual comfort during clinical operations:

1. **Brand Identity Palette**:
   - **Soft Pale Ice (`#E7F0FA`)**: Primary typography highlights, light mode background elements.
   - **Steel Sky (`#7BA4D0`)**: Secondary accent glows, section indicators, active tab indicators.
   - **Royal Sapphire (`#2E5E99`)**: Primary brand actions, score gauges, top navigation highlights.
   - **Midnight Navy (`#0D2440`)**: Ground foundation and extruded card base.

2. **Monomorphic Soft-UI (Neumorphic Dark & Light Design)**:
   - Elements are visually extruded from or debossed into a continuous dark/light canvas.
   - Extruded Cards (`mono-card` & `mono-card-interactive`): Dual-shadow offset (`box-shadow: 8px 8px 22px rgba(4, 12, 23, 0.85), -6px -6px 18px rgba(46, 94, 153, 0.25)`).
   - Sunken Tracks (`mono-inset`): Sunk-in inner shadows for inputs, filter toolbars, and metadata counters.
   - Tactile Buttons (`mono-button` & `mono-button-primary`): 3D physical press states.

3. **Bilingual Internationalization (Arabic & English)**:
   - **Instant Language Switching**: Header button (`EN` / `العربية`) switches interface language dynamically.
   - **Full RTL Support**: Automates `<html dir="rtl" lang="ar">`, layout mirroring, and font switching to Google Fonts **Tajawal** & **Cairo** for natural Arabic reading.
   - **Medical Translation Dictionary** ([frontend/lib/translations.ts](file:///c:/Users/C-LAB/Videos/ai%20hackthon/frontend/lib/translations.ts)): Translates all UI components, search placeholders, filter tabs, citation labels, and quick clinical exemplars.

4. **Light & Dark Mode**:
   - Integrated `ThemeToggle` component with `localStorage` persistence.
   - Zero-flash anti-FOUC initialization script executed inside `<head>` prior to hydration.

---

## 📊 Data Model & Provenance Schemas

Entities defined in [backend/app/models.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/models.py) enforce ChromaDB compatibility rules: **zero null values; missing strings default to `""`**.

```text
SourceDocument (1) ──< (many) Chunk
       │                        │
       │                        └──< (many) RetrievalResult   [per query, transient]
       │
       └──< referenced by GoldenQuestion.expected_doc_id

IndexManifest (1) ── describes ──> whole Chunk collection
```

### Key Schemas Summary

1. **SourceDocument** ([data/sources.yaml](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/sources.yaml)): `doc_id`, `document_name`, `filename`, `publisher`, `publication_year`, `source_url`, `document_type`, `credibility_note`, `license_note`.
2. **Chunk** ([ChromaDB Vector Store Entry](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/index)):
   - Primary ID: `chunk_id` (e.g. `nice_ng243_p09_c03`)
   - Text Content: `text`
   - Metadata: `doc_id`, `document_name`, `page_number`, `section_title`, `section_number`, `subsection_title`, `recommendation_ids`, `source_url`, `document_type`, `publication_year`, `requires_caution`, `token_count`, `is_oversized`.
3. **IndexManifest** ([data/index/manifest.json](file:///c:/Users/C-LAB/Videos/ai%20hackthon/data/index/manifest.json)): `built_at`, `embedding_model`, `embedding_dimensions`, `chunk_target_tokens`, `document_count`, `chunk_count`, `per_document` statistics.
4. **RetrievalResult**: `chunk` (Chunk schema), `score` (Cosine similarity $1 - \text{distance}$), `rank` (1-indexed), `below_floor` (boolean flag).

---

## 🚀 Operations & Quickstart Guide

### 1. Prerequisites

- **Python**: `3.13` or higher
- **Node.js**: `20.x` or `24.x`
- **OpenRouter / OmniRoute API Key**

### ⚡ One-Click Windows Launch ([start.bat](file:///c:/Users/C-LAB/Videos/ai%20hackthon/start.bat))

Run `start.bat` from the repository root. It includes **skip-if-installed** checks to ensure fast launch times:

```cmd
start.bat
```

The script automatically:
1. Creates `.venv` if missing.
2. Checks if Python dependencies (`fastapi`, `uvicorn`, `chromadb`, `pymupdf`, `tiktoken`) are installed—skips `pip install` if present!
3. Creates `.env` from `.env.example` if missing.
4. Checks if `frontend/node_modules` exists—skips `npm install` if present!
5. Launches FastAPI backend (`:8000`) and Next.js frontend (`:3000`) concurrently in separate windows.

---

### 2. Manual Commands

```bash
# 1. Activate Virtual Environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install Python Dependencies
pip install -r requirements.txt

# 3. Install Frontend Dependencies
cd frontend
npm install
cd ..

# 4. Ingest Guideline Corpus
python -m backend.app.cli ingest

# 5. Start FastAPI Backend (Port 8000)
uvicorn backend.app.main:app --reload --port 8000

# 6. Start Next.js Frontend Inspector (Port 3000)
cd frontend
npm run dev
```

Open **`http://localhost:3000`** in your browser.

---

## 💻 CLI Command Reference

The system includes a CLI interface via [backend/app/cli.py](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/cli.py).

### 1. Ingest Guidelines (`ingest`)

```bash
python -m backend.app.cli ingest [--dry-run] [--doc-id DOC_ID] [--verbose]
```

- `--dry-run`: Parse, clean, and chunk without embedding or writing vectors.
- `--doc-id`: Limit ingestion to a specific registered document ID.
- `--verbose`: Output per-page parsing diagnostics.

**Exit Codes**:
| Code | Meaning |
|---|---|
| `0` | Success — Ingestion complete / Eval hit-rate $\ge 80\%$ |
| `1` | Unregistered PDF present in corpus directory |
| `2` | Scanned / No-text layer PDF |
| `3` | No sections detected in document |
| `4` | Embedding provider failure after retries |
| `5` | Configuration / Missing API key error |

### 2. Query Evidence (`query`)

```bash
python -m backend.app.cli query "What is the emergency management of adrenal crisis?" --top-k 5 --full-text
```

### 3. Golden Evaluation (`eval`)

```bash
python -m backend.app.cli eval [--top-k 5] [--json]
```

Runs the retrieval quality suite over the golden question set in [backend/tests/eval/golden_questions.yaml](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/tests/eval/golden_questions.yaml). Target: $\ge 80\%$ hit rate in top-5 results.

---

## 🌐 API Specification

### Implemented Endpoints

#### 1. `GET /api/health`
Checks server status and index readiness.

#### 2. `POST /api/search`
Retrieves top-K guideline chunks for a clinical query with relevance scores and structural metadata.

```json
{
  "query": "What are the clinical signs of primary adrenal insufficiency?",
  "top_k": 5
}
```

#### 3. `GET /api/index`
Returns index metadata (`built_at`, `embedding_model`, `chunk_count`, `document_count`).

#### 4. `GET /api/sources`
Returns all registered source documents and credibility justifications.

#### 5. `POST /api/generate`
Returns **`501 Not Implemented`** stub by design (Constitution Principle V).

---

## 🧪 Testing & Quality Verification

Run the test suite using `pytest`:

```bash
# Run unit, integration, and golden evaluation tests
pytest backend/tests/ -v
```

---

## 📁 Project Structure

```text
ai-hackthon/
├── README.md                                  # Full system specification & architecture guide
├── Sapphire_VEIL_Comprehensive_Documentation.docx  # Generated Word document specification
├── start.bat                                  # Fast 1-click Windows project launcher
├── generate_docx.js                           # Node script to build Word documentation
├── requirements.txt                           # Backend Python dependencies
├── .env.example                               # Environment configuration template
├── data/
│   ├── corpus/                                # Registered guideline PDFs (NICE NG243)
│   ├── sources.yaml                           # Provenance & credibility registry
│   └── index/                                 # Persistent ChromaDB vector store & manifest.json
├── backend/
│   ├── app/
│   │   ├── main.py                            # FastAPI app entry & static mount
│   │   ├── config.py                          # Pydantic-settings configuration
│   │   ├── models.py                          # Pydantic data schemas
│   │   ├── cli.py                             # CLI interface (ingest, query, eval)
│   │   ├── errors.py                          # Typed system errors & exit codes
│   │   ├── api/
│   │   │   ├── search.py                      # Search, health, index & sources endpoints
│   │   │   └── generate.py                    # 501 Stub for Day 2 generation
│   │   ├── ingestion/
│   │   │   ├── registry.py                    # Sources.yaml validator
│   │   │   ├── parser.py                      # PyMuPDF span-level PDF extractor
│   │   │   ├── cleaner.py                     # Frequency boilerplate cleaner & glyph repair
│   │   │   ├── sectioner.py                   # NICE hierarchy detector (1.1 / 1.1.1)
│   │   │   ├── chunker.py                     # Atomic recommendation chunker
│   │   │   └── pipeline.py                    # Pipeline orchestrator
│   │   ├── retrieval/
│   │   │   ├── base.py                        # Retriever protocol seam
│   │   │   ├── dense.py                       # Cosine top-K ChromaDB retriever
│   │   │   └── store.py                       # ChromaDB persistent store client
│   │   └── embeddings/
│   │       ├── base.py                        # Embedder protocol seam
│   │       └── openrouter.py                  # OpenRouter batched embedding client
│   └── tests/
│       ├── unit/                              # Cleaner, sectioner, chunker unit tests
│       ├── integration/                       # Pipeline & search latency integration tests
│       └── eval/
│           ├── golden_questions.yaml          # Golden clinical question dataset
│           └── test_retrieval_quality.py      # Automated retrieval hit-rate test
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                         # Root layout with persistent disclaimer banner & header
│   │   ├── page.tsx                           # Retrieval Inspector UI page
│   │   └── globals.css                        # Monomorphic CSS styling & theme variables
│   ├── components/
│   │   ├── SearchBox.tsx                      # Query input component with exemplars
│   │   ├── ChunkCard.tsx                      # Ranked evidence card with citation copy
│   │   ├── IndexStatus.tsx                    # Index status & document counter
│   │   ├── ThemeToggle.tsx                    # Light/Dark mode switcher
│   │   └── LanguageToggle.tsx                 # Bilingual EN / العربية toggle
│   ├── lib/
│   │   ├── api.ts                             # Typed API client for FastAPI backend
│   │   └── translations.ts                    # English & Arabic medical translation dictionary
│   └── next.config.ts                         # Dev rewrite proxy (/api/* -> :8000)
└── specs/
    └── 001-clinical-rag-ingestion/            # Feature specification & architectural docs
        ├── spec.md                            # Feature Specification
        ├── plan.md                            # Implementation Plan
        ├── research.md                        # Phase 0 Research & Technical Decisions
        ├── data-model.md                      # Data Model Specification
        ├── quickstart.md                      # Quickstart & Gate Validation Guide
        ├── tasks.md                           # Project Task Tracking
        └── contracts/                         # OpenAPI and CLI contracts
```

---

## 📄 Licensing & Clinical Disclaimer

### Source Copyright
- **NICE Guideline NG243**: *Adrenal insufficiency: identification and management* (Published 28 August 2024). © NICE 2024. Subject to the [NICE Notice of Rights](https://www.nice.org.uk/terms-and-conditions#notice-of-rights). Reproduced for non-commercial educational & research use within this clinical hackathon prototype.

### Medical & Regulatory Disclaimer
> ⚠️ **IMPORTANT NOTICE**:
> This software is a **decision-support research prototype** designed to assist healthcare professionals in retrieving guideline evidence. It is **NOT** a diagnostic service, emergency triage tool, or direct patient advisory system. All retrieved evidence must be evaluated by a qualified medical professional prior to clinical decision-making.
