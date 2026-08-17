"""Golden-set retrieval evaluation (FR-031, FR-032, SC-003, Day 2 Lab).

Evaluates retrieval quality across:
- Hit Rate (presence of expected section in top-K)
- Mean Hit Rank (average position of first relevant evidence)
- Precision@3 and Precision@5 (density of relevant evidence in top-K)
- Chunk-level relevance inspection & failure mode diagnosis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, GoldenQuestion, RetrievalResult
from backend.app.retrieval.base import Retriever

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden_questions.yaml"

# SC-003: at least 80% of questions must retrieve their expected section in top-K.
TARGET_HIT_RATE = 0.80


def load_golden_questions(path: Path | None = None) -> list[GoldenQuestion]:
    source = path or GOLDEN_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return [GoldenQuestion(**entry) for entry in raw.get("questions", [])]


def is_chunk_relevant(chunk: Chunk, question: GoldenQuestion) -> bool:
    """Determine if a retrieved chunk contains ground-truth evidence for the question."""
    if chunk.doc_id != question.expected_doc_id:
        return False

    expected_sections = set(question.expected_sections)
    if chunk.section_number in expected_sections:
        return True

    # Also match if section number prefix matches (e.g. '1.7' matches '1.7.1')
    for sec in expected_sections:
        if chunk.section_number.startswith(sec) or sec.startswith(chunk.section_number):
            return True

    # Check recommendation IDs if specified
    if question.expected_recommendation_ids and chunk.recommendation_ids:
        chunk_recs = {r.strip() for r in chunk.recommendation_ids.split(",") if r.strip()}
        if any(r in chunk_recs for r in question.expected_recommendation_ids):
            return True

    return False


@dataclass
class RetrievedChunkInspection:
    chunk_id: str
    rank: int
    score: float
    page_number: int
    section_number: str
    section_title: str
    subsection_title: str
    recommendation_ids: str
    text_excerpt: str
    is_relevant: bool


@dataclass
class QuestionOutcome:
    question: GoldenQuestion
    hit: bool
    rank: int | None  # rank of the first matching chunk, 1-indexed
    top_score: float
    retrieved_sections: list[str]
    retrieved_chunks: list[RetrievedChunkInspection] = field(default_factory=list)
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    notes: str = ""

    @property
    def status(self) -> str:
        return "HIT" if self.hit else "MISS"


@dataclass
class EvaluationReport:
    outcomes: list[QuestionOutcome]
    top_k: int
    retriever_name: str = "Dense"
    chunking_config: str = "Section-Aware"

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def hits(self) -> int:
        return sum(1 for o in self.outcomes if o.hit)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    @property
    def mean_hit_rank(self) -> float:
        ranks = [o.rank for o in self.outcomes if o.hit and o.rank]
        return sum(ranks) / len(ranks) if ranks else 0.0

    @property
    def mean_precision_at_3(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.precision_at_3 for o in self.outcomes) / len(self.outcomes)

    @property
    def mean_precision_at_5(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.precision_at_5 for o in self.outcomes) / len(self.outcomes)

    @property
    def passed(self) -> bool:
        return self.hit_rate >= TARGET_HIT_RATE

    @property
    def misses(self) -> list[QuestionOutcome]:
        return [o for o in self.outcomes if not o.hit]

    def to_markdown_matrix(self) -> str:
        """Generate a formatted markdown matrix matching Day 2 requirements."""
        lines = [
            f"### Evaluation Tracking Matrix ({self.retriever_name} - {self.chunking_config}, Top-{self.top_k})\n",
            f"**Overall Hit Rate**: `{self.hit_rate:.1%}` ({self.hits}/{self.total}) | "
            f"**Mean Hit Rank**: `{self.mean_hit_rank:.2f}` | "
            f"**Mean P@3**: `{self.mean_precision_at_3:.2f}` | "
            f"**Mean P@5**: `{self.mean_precision_at_5:.2f}`\n",
            "| Query # | Query Description | Chunking Config | Top-$k$ | Precision@3 | Precision@5 | Notes / Failure Modes |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :--- |",
        ]
        for o in self.outcomes:
            q_text = o.question.question
            if len(q_text) > 42:
                q_text = q_text[:39] + "..."
            failure_note = o.notes or (
                "Ground-truth section retrieved" if o.hit else f"Expected {','.join(o.question.expected_sections)}, got {','.join(o.retrieved_sections[:3])}"
            )
            lines.append(
                f"| **{o.question.id}** | *{q_text}* | {self.chunking_config} | {self.top_k} | "
                f"${o.precision_at_3:.2f}$ | ${o.precision_at_5:.2f}$ | {failure_note} |"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "retriever_name": self.retriever_name,
            "chunking_config": self.chunking_config,
            "top_k": self.top_k,
            "total": self.total,
            "hits": self.hits,
            "hit_rate": round(self.hit_rate, 4),
            "mean_hit_rank": round(self.mean_hit_rank, 2),
            "mean_precision_at_3": round(self.mean_precision_at_3, 4),
            "mean_precision_at_5": round(self.mean_precision_at_5, 4),
            "passed": self.passed,
            "questions": [
                {
                    "id": o.question.id,
                    "question": o.question.question,
                    "status": o.status,
                    "rank": o.rank,
                    "top_score": round(o.top_score, 4),
                    "precision_at_3": round(o.precision_at_3, 4),
                    "precision_at_5": round(o.precision_at_5, 4),
                    "expected_sections": o.question.expected_sections,
                    "retrieved_sections": o.retrieved_sections,
                    "notes": o.notes,
                }
                for o in self.outcomes
            ],
        }


def evaluate(
    retriever: Retriever,
    questions: list[GoldenQuestion] | None = None,
    top_k: int | None = None,
    settings: Settings | None = None,
    retriever_name: str = "Dense",
    chunking_config: str = "Section-Aware",
) -> EvaluationReport:
    """Run every golden question and record metrics (Hit Rate, Precision@3, Precision@5)."""
    settings = settings or get_settings()
    questions = questions or load_golden_questions()
    k = max(top_k or settings.top_k, 5)  # retrieve at least 5 for Precision@5 calculation

    outcomes: list[QuestionOutcome] = []
    for question in questions:
        results = retriever.search(question.question, k)

        inspections: list[RetrievedChunkInspection] = []
        hit_rank: int | None = None
        relevant_in_top_3 = 0
        relevant_in_top_5 = 0

        for idx, result in enumerate(results):
            relevant = is_chunk_relevant(result.chunk, question)
            if relevant:
                if hit_rank is None:
                    hit_rank = result.rank
                if idx < 3:
                    relevant_in_top_3 += 1
                if idx < 5:
                    relevant_in_top_5 += 1

            inspections.append(
                RetrievedChunkInspection(
                    chunk_id=result.chunk.chunk_id,
                    rank=result.rank,
                    score=result.score,
                    page_number=result.chunk.page_number,
                    section_number=result.chunk.section_number,
                    section_title=result.chunk.section_title,
                    subsection_title=result.chunk.subsection_title,
                    recommendation_ids=result.chunk.recommendation_ids,
                    text_excerpt=result.chunk.text[:120].replace("\n", " "),
                    is_relevant=relevant,
                )
            )

        p_at_3 = relevant_in_top_3 / 3.0 if len(results) >= 3 else (relevant_in_top_3 / max(len(results), 1))
        p_at_5 = relevant_in_top_5 / 5.0 if len(results) >= 5 else (relevant_in_top_5 / max(len(results), 1))

        # Diagnose failure mode if missed or low precision
        note = ""
        if hit_rank is None:
            got_secs = ",".join(r.chunk.section_number for r in results[:3] if r.chunk.section_number)
            note = f"Missed target section {','.join(question.expected_sections)}; retrieved {got_secs or 'unsectioned'}"
        elif p_at_5 < 0.4:
            note = "High semantic drift in lower ranks"
        else:
            note = "High-precision guideline evidence captured"

        outcomes.append(
            QuestionOutcome(
                question=question,
                hit=hit_rank is not None,
                rank=hit_rank,
                top_score=results[0].score if results else 0.0,
                retrieved_sections=[r.chunk.section_number for r in results],
                retrieved_chunks=inspections,
                precision_at_3=p_at_3,
                precision_at_5=p_at_5,
                notes=note,
            )
        )

    return EvaluationReport(
        outcomes=outcomes,
        top_k=top_k or settings.top_k,
        retriever_name=retriever_name,
        chunking_config=chunking_config,
    )
