"""Detects clinically ambiguous queries and suggests targeted follow-up questions.

A dosing question that never says whether the patient is an adult or a child,
or whether this is routine replacement versus an emergency, is answerable
only by picking a branch of the guideline and hoping it is the right one.
This module flags that ambiguity so the UI can ask before the model guesses,
rather than after an answer has already committed to one reading.

Deliberately narrow: false negatives (missing an ambiguous query) just mean
no prompt is shown, which is safe. False positives (nagging a clearly-scoped
query) erode trust fast, so every trigger requires the query to already be
about a clinical action -- dosing, route, or timing -- before it fires.
"""

from __future__ import annotations

import re

_DOSING_TOPIC = re.compile(
    r"\bdos(?:e|es|ing|age)\b|\bhydrocortisone\b|\bprednisolone\b|\bglucocorticoid\b|"
    r"\bsteroid\b|\bmineralocorticoid\b|\bfludrocortisone\b",
    re.IGNORECASE,
)

_AGE_GROUP_MENTIONED = re.compile(
    r"\badult\w*\b|\bchild\w*\b|\bp(?:a)?ediatric\w*\b|\binfant\w*\b|\bneonat\w*\b|"
    r"\byoung\ person\b|\bunder\s*16\b|\bover\s*16\b",
    re.IGNORECASE,
)

_CLINICAL_CONTEXT_MENTIONED = re.compile(
    r"\bcrisis\b|\bemergency\b|\bsick[\s-]?day\b|\bsurger\w*\b|\bperioperative\b|"
    r"\broutine\b|\bmaintenance\b|\bwithdrawal\b|\btapering\b|\bstress\ dos\w*\b|"
    r"\bintercurrent\ illness\b",
    re.IGNORECASE,
)

# Signals that the guideline's own text was quoted back verbatim, which
# already carries whatever scoping it needed -- not worth interrupting.
_QUOTES_GUIDELINE = re.compile(r"\[source\s*\d|\[\d+(?:\.\d+)+\]", re.IGNORECASE)

MAX_QUESTIONS = 2


def suggest_clarifying_questions(query: str) -> list[str]:
    """Return up to `MAX_QUESTIONS` follow-ups if the query is ambiguously scoped.

    Only fires for queries that are already about a dosing-adjacent clinical
    action (`_DOSING_TOPIC`); everything else -- diagnosis, symptoms, general
    background -- is left alone, since ambiguity there doesn't risk steering
    a clinician toward the wrong dose or route.
    """
    if not query or _QUOTES_GUIDELINE.search(query):
        return []

    if not _DOSING_TOPIC.search(query):
        return []

    questions: list[str] = []

    if not _AGE_GROUP_MENTIONED.search(query):
        questions.append("Is this for an adult, or for a child/young person under 16?")

    if not _CLINICAL_CONTEXT_MENTIONED.search(query):
        questions.append(
            "What clinical situation is this for -- routine daily replacement, "
            "sick-day dosing, perioperative cover, or emergency adrenal crisis "
            "management?"
        )

    return questions[:MAX_QUESTIONS]
