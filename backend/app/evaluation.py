"""Golden-set retrieval evaluation (FR-031, FR-032, SC-003).

Turns the brief's "run 5-10 clinical questions" gate into a repeatable measurement.
Without a hit rate, Day 2 chunking and retrieval changes are unmeasurable — you cannot
tell an improvement from a regression.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.app.config import Settings, get_settings
from backend.app.models import GoldenQuestion
from backend.app.retrieval.base import Retriever

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden_questions.yaml"

# SC-003: at least 8 of 10 questions must retrieve their expected section in top-K.
TARGET_HIT_RATE = 0.80


def load_golden_questions(path: Path | None = None) -> list[GoldenQuestion]:
    source = path or GOLDEN_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return [GoldenQuestion(**entry) for entry in raw.get("questions", [])]


@dataclass
class QuestionOutcome:
    question: GoldenQuestion
    hit: bool
    rank: int | None  # rank of the first matching chunk, 1-indexed
    top_score: float
    retrieved_sections: list[str]

    @property
    def status(self) -> str:
        return "HIT" if self.hit else "MISS"


@dataclass
class EvaluationReport:
    outcomes: list[QuestionOutcome]
    top_k: int

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
    def passed(self) -> bool:
        return self.hit_rate >= TARGET_HIT_RATE

    @property
    def misses(self) -> list[QuestionOutcome]:
        return [o for o in self.outcomes if not o.hit]


def evaluate(
    retriever: Retriever,
    questions: list[GoldenQuestion] | None = None,
    top_k: int | None = None,
    settings: Settings | None = None,
) -> EvaluationReport:
    """Run every golden question and record whether its expected section appeared."""
    settings = settings or get_settings()
    questions = questions or load_golden_questions()
    k = top_k or settings.top_k

    outcomes: list[QuestionOutcome] = []
    for question in questions:
        results = retriever.search(question.question, k)

        expected = set(question.expected_sections)
        hit_rank: int | None = None
        for result in results:
            if (
                result.chunk.doc_id == question.expected_doc_id
                and result.chunk.section_number in expected
            ):
                hit_rank = result.rank
                break

        outcomes.append(
            QuestionOutcome(
                question=question,
                hit=hit_rank is not None,
                rank=hit_rank,
                top_score=results[0].score if results else 0.0,
                retrieved_sections=[r.chunk.section_number for r in results],
            )
        )

    return EvaluationReport(outcomes=outcomes, top_k=k)
