"""Scope classification for retrieval results.

Separates "we found supporting evidence" from "this question is not about
the indexed corpus at all", so the API and the CLI answer identically.

Three states:

    in_scope     at least one result is above the evidence floor
    no_evidence  related enough to the corpus, but nothing above the floor
    out_of_scope top score is below the scope threshold

Only `out_of_scope` suppresses results, so an unrelated question cannot be
answered with unrelated guideline text.
"""

from __future__ import annotations

from backend.app.models import RetrievalResult

OUT_OF_SCOPE_MESSAGE = (
    "This question is outside the current scope of Eva AI. "
    "Eva AI currently covers adrenal insufficiency, including its "
    "identification and management, based on the registered NICE NG243 "
    "guideline."
)

NO_EVIDENCE_MESSAGE = (
    "The question appears related to the current clinical topic, but no "
    "strong supporting evidence was found in the registered guideline."
)

IN_SCOPE_MESSAGE = "Relevant clinical evidence was found in the registered guideline."


def classify_scope(
    results: list[RetrievalResult],
    scope_threshold: float,
) -> tuple[str, str, list[RetrievalResult]]:
    """Classify a result set, returning (status, message, results_to_show)."""
    # Compare against the absolute relevance signal, not `score`: the hybrid
    # retriever normalises RRF by the top hit, so `results[0].score` is 1.0 for
    # every query and would classify anything as in_scope.
    top_score = results[0].absolute_relevance if results else 0.0
    above_floor = sum(1 for result in results if not result.below_floor)

    if not results or top_score < scope_threshold:
        return "out_of_scope", OUT_OF_SCOPE_MESSAGE, []

    if above_floor > 0:
        return "in_scope", IN_SCOPE_MESSAGE, results

    return "no_evidence", NO_EVIDENCE_MESSAGE, results
