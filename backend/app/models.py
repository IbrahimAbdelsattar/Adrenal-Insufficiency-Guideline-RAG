"""Shared Pydantic schemas.

Field names, types and validation rules come from data-model.md.

ChromaDB metadata values must be scalars (str/int/float/bool) and may not be null,
so optional-by-meaning fields use "" rather than None. `Chunk.to_metadata()` is the
single place that shape is produced.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Chunks whose source is not a current guideline get flagged for the UI.
CAUTION_AGE_YEARS = 10

PLACEHOLDER_TOKENS = {"", "todo", "tbd", "n/a", "na", "...", "xxx"}


class DocumentType(StrEnum):
    GUIDELINE = "guideline"
    BULLETIN = "bulletin"
    REVIEW = "review"
    OTHER = "other"


class SourceDocument(BaseModel):
    """A registered guideline PDF, declared by hand in data/sources.yaml."""

    doc_id: str = Field(pattern=r"^[a-z0-9_]+$")
    document_name: str
    filename: str
    publisher: str
    publication_year: int
    source_url: str
    document_type: DocumentType
    credibility_note: str
    license_note: str

    @field_validator("credibility_note", "license_note")
    @classmethod
    def _reject_placeholder(cls, v: str) -> str:
        if v.strip().lower() in PLACEHOLDER_TOKENS:
            raise ValueError(
                "must be a real justification, not a placeholder (Constitution Principle III)"
            )
        return v.strip()

    def requires_caution(self, now_year: int | None = None) -> bool:
        """True when this source is not a current clinical guideline (FR-003)."""
        year = now_year if now_year is not None else datetime.now().year
        return (
            self.document_type is not DocumentType.GUIDELINE
            or self.publication_year < year - CAUTION_AGE_YEARS
        )


class Chunk(BaseModel):
    """An indexed unit of guideline text. One ChromaDB entry each."""

    chunk_id: str
    text: str

    # Denormalised from SourceDocument so retrieval needs no second lookup.
    document_name: str
    doc_id: str
    source_url: str
    document_type: str
    publication_year: int
    requires_caution: bool

    # Location, for human trace-back.
    page_number: int
    section_title: str = ""
    section_number: str = ""
    subsection_title: str = ""
    recommendation_ids: str = ""

    token_count: int = 0
    is_oversized: bool = False

    def to_metadata(self) -> dict[str, Any]:
        """Flat, scalar, null-free metadata for ChromaDB (FR-015, FR-017)."""
        return {
            "document_name": self.document_name,
            "doc_id": self.doc_id,
            "source_url": self.source_url,
            "document_type": self.document_type,
            "publication_year": self.publication_year,
            "requires_caution": self.requires_caution,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "section_number": self.section_number,
            "subsection_title": self.subsection_title,
            "recommendation_ids": self.recommendation_ids,
            "token_count": self.token_count,
            "is_oversized": self.is_oversized,
        }

    @classmethod
    def from_stored(
        cls,
        chunk_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> Chunk:
        """Rebuild a Chunk from what ChromaDB gives back."""
        return cls(chunk_id=chunk_id, text=text, **metadata)


class RetrievalResult(BaseModel):
    """A chunk paired with its score for one query. Not persisted."""

    chunk: Chunk
    score: float
    rank: int
    below_floor: bool

    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    retriever_mode: str = "dense"


class PerDocumentStats(BaseModel):
    doc_id: str
    pages_processed: int
    pages_empty: int
    chunk_count: int


class IndexManifest(BaseModel):
    """Written to data/index/manifest.json so an index is self-describing."""

    built_at: datetime
    embedding_model: str
    embedding_dimensions: int
    chunk_target_tokens: int
    chunk_min_tokens: int
    chunk_max_tokens: int
    document_count: int
    chunk_count: int
    oversized_chunk_count: int
    per_document: list[PerDocumentStats] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Response body for POST /api/search."""

    query: str

    # Only populated when useful evidence is available.
    results: list[RetrievalResult]

    result_count: int

    # True only when at least one result is above the evidence floor.
    evidence_found: bool

    # New scope classification:
    # - in_scope: question is related to the system's topic
    # - no_evidence: likely related, but no strong evidence was found
    # - out_of_scope: question is unrelated to the system's topic
    scope_status: Literal[
        "in_scope",
        "no_evidence",
        "out_of_scope",
    ]

    # Human-readable message for the frontend.
    scope_message: str = ""

    embedding_model: str = ""
    latency_ms: int = 0
    disclaimer: str


class GenerateRequest(BaseModel):
    """Request body for POST /api/generate."""

    query: str
    top_k: int | None = Field(default=None)


class GenerateResponse(BaseModel):
    """Response body for POST /api/generate."""

    query: str
    answer: str
    citations: list[dict]
    evidence_found: bool
    disclaimer: str
    model: str
    latency_ms: int


class GoldenQuestion(BaseModel):
    """Evaluation fixture (backend/tests/eval/golden_questions.yaml)."""

    id: str
    question: str
    expected_doc_id: str
    expected_sections: list[str] = Field(default_factory=list)
    expected_recommendation_ids: list[str] = Field(default_factory=list)
    notes: str = ""


DISCLAIMER = (
    "Decision-support aid for qualified clinical users. Answers are drawn only from "
    "the ingested official guidelines shown. This is not a diagnostic tool and must "
    "not be used for emergency medical decisions."
)
