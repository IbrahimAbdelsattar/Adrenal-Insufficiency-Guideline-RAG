const fs = require('fs');
const path = require('path');
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  Header,
  Footer,
  AlignmentType,
  LevelFormat,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
  PageBreak,
  Bookmark
} = require('docx');

// Colors matching Eva AI brand system
const BRAND_NAVY = "0D2440";
const BRAND_ROYAL = "2E5E99";
const BRAND_STEEL = "7BA4D0";
const BRAND_ICE = "E7F0FA";
const BRAND_BORDER = "C2D6EC";
const BRAND_BG_LIGHT = "F0F5FA";
const BRAND_TEXT_DARK = "0D2440";
const BRAND_TEXT_MUTED = "4A72A3";

// Cell borders config
const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: "CBD5E1" };
const cellBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };

// Callout border (thick left border)
const calloutBorders = {
  left: { style: BorderStyle.SINGLE, size: 24, color: BRAND_ROYAL },
  top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }
};

// Paragraph Helper Functions
function createTitle() {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 360, after: 120 },
    children: [
      new TextRun({ text: "Eva ", font: "Arial", size: 44, bold: true, color: BRAND_ROYAL }),
      new TextRun({ text: "AI", font: "Arial", size: 44, bold: true, color: BRAND_NAVY }),
    ]
  });
}

function createSubtitle(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 360 },
    children: [
      new TextRun({ text, font: "Arial", size: 22, italic: true, color: BRAND_TEXT_MUTED })
    ]
  });
}

function createHeading1(text, bookmarkId) {
  const children = [];
  if (bookmarkId) {
    children.push(new Bookmark({ id: bookmarkId, children: [new TextRun({ text, font: "Arial", size: 28, bold: true, color: BRAND_NAVY })] }));
  } else {
    children.push(new TextRun({ text, font: "Arial", size: 28, bold: true, color: BRAND_NAVY }));
  }
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 180 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: BRAND_ROYAL, space: 4 } },
    children
  });
}

function createHeading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120 },
    children: [
      new TextRun({ text, font: "Arial", size: 24, bold: true, color: BRAND_ROYAL })
    ]
  });
}

function createHeading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 180, after: 80 },
    children: [
      new TextRun({ text, font: "Arial", size: 22, bold: true, color: BRAND_NAVY })
    ]
  });
}

function createBody(text, options = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 120, line: 276 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 22,
        color: options.color || BRAND_TEXT_DARK,
        bold: options.bold || false,
        italic: options.italic || false,
      })
    ]
  });
}

function createCallout(title, text) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: calloutBorders,
            width: { size: 9360, type: WidthType.DXA },
            shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR },
            margins: { top: 140, bottom: 140, left: 200, right: 180 },
            children: [
              new Paragraph({
                spacing: { before: 0, after: 60 },
                children: [new TextRun({ text: title, font: "Arial", size: 22, bold: true, color: BRAND_ROYAL })]
              }),
              new Paragraph({
                spacing: { before: 0, after: 0, line: 260 },
                children: [new TextRun({ text: text, font: "Arial", size: 20, italic: true, color: BRAND_TEXT_DARK })]
              })
            ]
          })
        ]
      })
    ]
  });
}

// Build Document
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22, color: BRAND_TEXT_DARK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 28, bold: true, font: "Arial", color: BRAND_NAVY }, paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 24, bold: true, font: "Arial", color: BRAND_ROYAL }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, font: "Arial", color: BRAND_NAVY }, paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
      },
      {
        reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
      }
    ]
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 }, // US Letter: 8.5 x 11 in
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } // 1 inch margins
        }
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              tabStops: [{ type: "right", position: 9360 }],
              border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BRAND_STEEL, space: 4 } },
              children: [
                new TextRun({ text: "Eva AI — Clinical Decision Support", font: "Arial", size: 18, bold: true, color: BRAND_ROYAL }),
                new TextRun({ text: "\tSystem Documentation & Blueprint", font: "Arial", size: 18, color: BRAND_TEXT_MUTED })
              ]
            })
          ]
        })
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              tabStops: [{ type: "right", position: 9360 }],
              border: { top: { style: BorderStyle.SINGLE, size: 4, color: BRAND_BORDER, space: 4 } },
              children: [
                new TextRun({ text: "Confidential · Evidence-Grounded RAG System", font: "Arial", size: 18, color: BRAND_TEXT_MUTED }),
                new TextRun({ text: "\tPage ", font: "Arial", size: 18, color: BRAND_TEXT_MUTED }),
                new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: BRAND_ROYAL, bold: true }),
                new TextRun({ text: " of ", font: "Arial", size: 18, color: BRAND_TEXT_MUTED }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], font: "Arial", size: 18, color: BRAND_TEXT_MUTED })
              ]
            })
          ]
        })
      },
      children: [
        // Title Block
        createTitle(),
        createSubtitle("Comprehensive Technical Blueprint & Non-Technical Executive Overview"),
        
        createCallout(
          "Executive Summary & Clinical Scope Statement",
          "This system helps clinicians and clinical trainees answer questions about adrenal insufficiency identification and management using NICE guideline NG243 and registered supporting official sources. Every retrieved chunk carries structural page-level citations, section titles, and recommendation numbers without automated hallucination."
        ),

        new Paragraph({ spacing: { before: 180, after: 180 } }),

        // 1. NON-TECHNICAL OVERVIEW
        createHeading1("1. Non-Technical Executive Overview", "sec1"),
        createHeading2("1.1 The Clinical Challenge"),
        createBody("Adrenal insufficiency (including Primary Addison's Disease and Secondary Adrenal Suppression) is a life-threatening endocrine disorder requiring rapid, highly precise diagnosis, emergency adrenal crisis management, and strict sick-day dosing protocols. Clinicians and trainees face complex, multi-page clinical guidelines (such as NICE NG243, published August 2024), where looking up specific dosage adjustments or diagnostic criteria during clinical rounds can be time-consuming and error-prone."),

        createHeading2("1.2 What is Eva AI?"),
        createBody("Eva AI (Clinical Decision Support Lite) is an advanced Retrieval-Augmented Generation (RAG) platform. Unlike generic AI chatbots that guess or synthesize answers with a risk of clinical hallucinations, Eva AI functions as a zero-hallucination evidence search engine. It ingests official clinical guideline PDFs, strips extraction noise while preserving page numbers, and retrieves the most relevant, un-altered clinical recommendation text."),

        createHeading2("1.3 Core Non-Technical Capabilities"),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "100% Traceable Citations: Every answer card displays the document name, exact page number, section title, and recommendation ID (e.g. Rec 1.2.1).", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Atomic Recommendation Preservation: Clinical recommendations are never cut mid-sentence or split across chunks.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Bilingual Internationalization: Seamless single-click switching between English and Arabic (dir=rtl) with full medical terms.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Monomorphic Soft UI & Dual Themes: A tactile, extruded 3D design available in Light Mode and Dark Mode for high visual comfort.", font: "Arial", size: 22 })] }),

        new Paragraph({ children: [new PageBreak()] }),

        // 2. CLINICAL CONSTITUTION & GOVERNANCE
        createHeading1("2. System Constitution & Governance Principles", "sec2"),
        createBody("The architecture enforces six strict constitutional principles to guarantee clinical safety and strict regulatory compliance:"),

        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2200, 7160],
          rows: [
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Principle", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Clinical Rule & Implementation", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "I. Evidence Grounded", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "No generation path exists that can bypass retrieval. Answers must be strictly grounded in verified guideline text.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "II. Structural Citations", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Citation metadata (document, page, section, recommendation) is stored natively inside ChromaDB vector entries, returning in a single call.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "III. Source Legitimacy", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Fail-closed provenance registry (data/sources.yaml). Unregistered PDFs are rejected immediately prior to parsing.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "IV. Scope Discipline", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Strictly limited to adrenal insufficiency (NICE NG243). Persistent clinical decision-support disclaimers are rendered across UI and API.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "V. Staged Delivery", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Retrieval baseline verified via golden-set evaluation before introducing LLM generation (/api/generate returns 501 stub).", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2200, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "VI. Human Verification", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7160, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Low-scoring chunks are flagged, never silently hidden. Every chunk provides explicit page-number trace-back to the source PDF.", font: "Arial", size: 20 })] })] }),
              ]
            }),
          ]
        }),

        new Paragraph({ spacing: { before: 180, after: 180 } }),

        // 3. SYSTEM ARCHITECTURE
        createHeading1("3. System Architecture & Component Topology", "sec3"),
        createHeading2("3.1 Topology & Runtime Processes"),
        createBody("The platform is designed as a monolithic repository with clean internal component boundaries:"),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Development Mode: Two concurrent processes — FastAPI backend running on port 8000 and Next.js 15 App Router running on port 3000 (with dev proxy rewrites for /api/*).", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Production Mode: Single deployable artifact where FastAPI serves the static frontend build export (frontend/out) via StaticFiles.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Protocol Seams: Ingestion, Retrieval, and Embedding layers are behind explicit Python Protocols (retrieval/base.py & embeddings/base.py) allowing seamless Day 2 swap for hybrid search or cross-encoder rerankers.", font: "Arial", size: 22 })] }),

        createHeading2("3.2 Technology Stack Matrix"),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2500, 3000, 3860],
          rows: [
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2500, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Component Layer", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Technology Selected", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3860, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Architectural Rationale", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Backend Framework", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "FastAPI + Uvicorn (Python 3.13)", font: "Arial", size: 20 })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "High performance async framework, automatic Pydantic v2 OpenAPI schema generation.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Vector Store", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "ChromaDB Persistent Client", font: "Arial", size: 20 })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Zero external server dependency; stores scalar citation metadata natively on vector entries.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Embedding Provider", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "OpenRouter (text-embedding-3-small)", font: "Arial", size: 20 })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "1536-dimensional embeddings, cost-efficient, single API key infrastructure.", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 2500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Frontend Framework", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3000, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Next.js 15 (React 19, TypeScript)", font: "Arial", size: 20 })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 3860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "App Router, Tailwind CSS, Monomorphic Soft-UI design, bilingual English/Arabic RTL.", font: "Arial", size: 20 })] })] }),
              ]
            }),
          ]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // 4. RAG INGESTION PIPELINE
        createHeading1("4. RAG Ingestion Pipeline & Algorithmic Mechanics", "sec4"),
        createBody("The ingestion pipeline converts multi-page clinical guideline PDFs into section-aware, citation-ready vector entries without losing clinical context. Below is the multi-stage transformation sequence:"),

        createHeading2("4.1 Ingestion Pipeline Stages"),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Fail-Closed Registry Check: Validates every PDF in data/corpus/ against data/sources.yaml. Unregistered PDFs immediately abort ingestion (Exit code 1).", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "PyMuPDF Span Extraction: PyMuPDF (fitz) extracts text spans while preserving font size, font weight, and 1-indexed source PDF page numbers.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Frequency-Based Cleaning: Lines appearing on >60% of pages (running footers, copyright notices) are automatically purged as boilerplate. Bullet glyphs and line-break hyphenations are repaired.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Hierarchy Detection: Detects N.N major sections (e.g. 1.2 Initial identification) and N.N.N recommendation numbers (e.g. 1.2.1).", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Atomic Recommendation Packing: Treat each numbered recommendation as an ATOMIC unit that is never split across chunks. Consecutive sibling recommendations are packed into token budgets of 400–800 tokens (tiktoken cl100k_base). Oversized atomic recommendations are emitted whole and flagged.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Batched Vector Embeddings: Generates 1536-dim embeddings via OpenRouter in batches of 100 with exponential backoff retries.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "Atomic Collection Swap: Updates ChromaDB collection atomically and writes manifest.json recording the embedding model, dimensions, build time, and document stats.", font: "Arial", size: 22 })] }),

        new Paragraph({ spacing: { before: 180, after: 180 } }),

        // 5. USER INTERFACE & BRAND IDENTITY
        createHeading1("5. Eva AI Visual System & User Experience", "sec5"),
        createHeading2("5.1 Monomorphic Soft-UI (Neumorphic Dark/Light)"),
        createBody("Eva AI introduces a custom Monomorphic Design System. Elements appear sculpted directly out of a single continuous canvas (#0D2440 in Dark Mode, #F0F5FA in Light Mode) using dual offset drop-shadows and debossed inner tracks."),

        createHeading2("5.2 Internationalization & Bilingual Arabic Support"),
        createBody("The platform provides full bilingual English and Arabic support:"),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Single-Click Language Toggle: Instant switching between English and Arabic (العربية).", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "RTL Directionality: Full dir=rtl layout adaptations, font switching to Google Tajawal & Cairo for Arabic typography.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "Bilingual Translations: Complete medical terminology translation dictionary (translations.ts).", font: "Arial", size: 22 })] }),

        new Paragraph({ children: [new PageBreak()] }),

        // 6. CLI & API REFERENCE
        createHeading1("6. CLI Interface & API Specifications", "sec6"),
        createHeading2("6.1 Command Line Interface (backend.app.cli)"),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "ingest [--dry-run] [--doc-id DOC] [--verbose]: Rebuild vector index from data/corpus/.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "query \"question\" [--top-k K] [--json] [--full-text]: Execute retrieval query from shell.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "eval [--top-k K] [--json]: Execute golden question retrieval test suite.", font: "Arial", size: 22 })] }),

        createHeading2("6.2 Exit Codes Matrix"),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [1500, 7860],
          rows: [
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Exit Code", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, shading: { fill: BRAND_NAVY, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "System Meaning", font: "Arial", size: 20, bold: true, color: "FFFFFF" })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "0", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Success — Ingestion completed / Golden evaluation hit rate >= 80%", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "1", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Unregistered PDF present in corpus directory (FR-002)", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "2", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "PDF has no extractable text layer (scanned PDF)", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "3", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "No sections detected in a guideline document", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "4", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Embedding provider failure after exponential backoff retries", font: "Arial", size: 20 })] })] }),
              ]
            }),
            new TableRow({
              children: [
                new TableCell({ borders: cellBorders, width: { size: 1500, type: WidthType.DXA }, shading: { fill: BRAND_BG_LIGHT, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "5", font: "Arial", size: 20, bold: true, color: BRAND_ROYAL })] })] }),
                new TableCell({ borders: cellBorders, width: { size: 7860, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, children: [new Paragraph({ children: [new TextRun({ text: "Configuration error (missing API key or invalid directory paths)", font: "Arial", size: 20 })] })] }),
              ]
            }),
          ]
        }),

        createHeading2("6.3 REST API Endpoint Specifications"),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "GET /api/health: Returns 200 OK with server status and index_ready boolean.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "POST /api/search: Accepts { query: string, top_k: int }, returns SearchResponse with ranked RetrievalResults, latency_ms, and disclaimer.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "GET /api/index: Returns IndexManifest metadata and document/chunk counts.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "GET /api/sources: Returns all registered SourceDocuments with credibility justifications.", font: "Arial", size: 22 })] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: [new TextRun({ text: "POST /api/generate: Returns 501 Not Implemented stub (Constitution Principle V).", font: "Arial", size: 22 })] }),

        new Paragraph({ spacing: { before: 180, after: 180 } }),

        // 7. EVALUATION & BENCHMARKING
        createHeading1("7. Quality Evaluation & Validation Framework", "sec7"),
        createBody("Retrieval quality is benchmarked against a golden clinical question dataset (backend/tests/eval/golden_questions.yaml) containing 10+ clinical queries over NICE NG243 sections 1.1 through 1.8."),

        createCallout(
          "Quality Metric & Benchmark Goal",
          "Target: Hit-rate >= 80% (at least 8 out of 10 clinical questions retrieve their expected guideline section within top-5 results). Evaluated automatically via pytest backend/tests/eval/."
        ),

        new Paragraph({ spacing: { before: 180, after: 180 } }),

        // 8. DEPLOYMENT & QUICKSTART
        createHeading1("8. Operations & Quickstart", "sec8"),
        createHeading2("8.1 One-Click Windows Launch (start.bat)"),
        createBody("Run start.bat from the repository root to automatically set up virtual environments, install dependencies, copy .env defaults, and launch both FastAPI (:8000) and Next.js (:3000) concurrently."),

        createHeading2("8.2 Manual Startup Commands"),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "python -m venv .venv && .venv\\Scripts\\activate && pip install -r requirements.txt", font: "Arial", size: 20 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "cd frontend && npm install && cd ..", font: "Arial", size: 20 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "python -m backend.app.cli ingest", font: "Arial", size: 20 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "uvicorn backend.app.main:app --reload --port 8000", font: "Arial", size: 20 })] }),
        new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: [new TextRun({ text: "cd frontend && npm run dev", font: "Arial", size: 20 })] }),

        new Paragraph({ spacing: { before: 360, after: 180 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "— End of System Specification Document —", font: "Arial", size: 20, italic: true, color: BRAND_TEXT_MUTED })
          ]
        })
      ]
    }
  ]
});

// Write .docx File
Packer.toBuffer(doc).then(buffer => {
  const outputPath = path.join(__dirname, 'Eva_AI_Comprehensive_Documentation.docx');
  fs.writeFileSync(outputPath, buffer);
  console.log('Successfully generated Eva_AI_Comprehensive_Documentation.docx at:', outputPath);
});
