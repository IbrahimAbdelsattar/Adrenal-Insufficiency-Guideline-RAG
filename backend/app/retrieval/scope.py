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

import re

from backend.app.models import RetrievalResult

# ---------------------------------------------------------------------------
# Refusal messages — "Honest, Not Unhelpful" format (Day 3 requirement)
#
# Each message does three things:
#   1. States clearly that the available evidence is insufficient
#   2. Explains what was searched, so the gap feels transparent, not evasive
#   3. Suggests a next step — rephrasing or consulting a clinician
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_MESSAGE = (
    "I couldn't find enough information in the indexed guidelines to answer this confidently. "
    "Eva AI searches NICE NG243 (adrenal insufficiency), and this question falls outside "
    "that guideline's domain entirely. "
    "Try rephrasing with adrenal insufficiency terminology, or consult a clinician directly."
)

NO_EVIDENCE_MESSAGE = (
    "I couldn't find enough information in the indexed guidelines to answer this confidently. "
    "Eva AI searched NICE NG243 but the retrieved evidence did not contain sufficient detail "
    "to address your specific question. "
    "Try rephrasing or broadening your clinical query, or consult a clinician directly."
)

IN_SCOPE_MESSAGE = "Relevant clinical evidence was found in the registered guideline."


_CLINICAL_DOMAIN_KEYWORDS = {
    "ng243",
    "nice",
    "guideline",
    "adrenal",
    "addison",
    "insufficiency",
    "crisis",
    "cortisol",
    "hydrocortisone",
    "fludrocortisone",
    "steroid",
    "glucocorticoid",
    "mineralocorticoid",
    "synacthen",
    "sst",
    "sick day",
    "hypoadrenalism",
    "prednisolone",
    "dexamethasone",
    "corticosteroid",
    "endocrine",
    "endocrinologist",
    "pituitary",
    "acth",
    "vomiting",
    "diarrhea",
    "hyponatremia",
    "hyperkalemia",
    "hypoglycemia",
    "hypotension",
    "tapering",
    "withdrawal",
    "primary",
    "secondary",
    "tertiary",
    # Arabic Clinical Terms
    "كظر",
    "كظرية",
    "أزمة",
    "أزمات",
    "قصور",
    "أديسون",
    "كورتيزول",
    "هيدروكورتيزون",
    "فلودروكورتيزون",
    "ستيرويد",
    "حمى",
    "أيام المرض",
    "قيء",
    "استفراغ",
    "وريد",
    "عضل",
    "حقن",
}


def is_clinical_domain_query(query: str) -> bool:
    """Return True if the query explicitly mentions NICE NG243 or clinical adrenal terminology."""
    if not query:
        return False
    lower_q = query.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", lower_q) for kw in _CLINICAL_DOMAIN_KEYWORDS)


def classify_scope(
    results: list[RetrievalResult],
    scope_threshold: float,
    query: str = "",
) -> tuple[str, str, list[RetrievalResult]]:
    """Classify a result set, returning (status, message, results_to_show)."""
    if not results:
        return "out_of_scope", OUT_OF_SCOPE_MESSAGE, []

    top_score = results[0].absolute_relevance
    has_domain_term = is_clinical_domain_query(query)

    # For queries referencing the guideline or clinical domain explicitly, allow broader overview matches
    effective_threshold = min(scope_threshold, 0.48) if has_domain_term else scope_threshold

    if top_score < effective_threshold:
        return "out_of_scope", OUT_OF_SCOPE_MESSAGE, []

    above_floor = sum(1 for result in results if not result.below_floor)
    if above_floor > 0 or has_domain_term:
        return "in_scope", IN_SCOPE_MESSAGE, results

    return "no_evidence", NO_EVIDENCE_MESSAGE, results
