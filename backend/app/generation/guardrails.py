"""Prompt injection and jailbreak detection for Eva-AI.

This module provides a deterministic, regex-based first-pass filter that runs
BEFORE retrieval and LLM calls. It catches adversarial inputs that attempt to
override the grounding constraints defined in the system prompt.

Constitution Principle V: Adversarial robustness must be implemented at the
application layer, not relied upon from the LLM alone.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection / jailbreak pattern library
# ---------------------------------------------------------------------------
# Each pattern is a compiled regex. Any match = injection detected.
# Patterns are case-insensitive and match across word boundaries where needed.

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Classic instruction-override phrases
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+instructions?", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|above|prior|earlier)\s+instructions?", re.I),
    re.compile(
        r"forget\s+(all\s+)?(previous|above|prior|earlier|your)\s+(instructions?|rules?|context)",
        re.I,
    ),
    re.compile(
        r"override\s+(your\s+)?(previous\s+)?(instructions?|rules?|constraints?|prompt)", re.I
    ),
    re.compile(
        r"bypass\s+(your\s+)?(safety|security|restrictions?|constraints?|rules?|guidelines?)", re.I
    ),
    # Persona-switching / DAN patterns
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\bact\s+as\s+(if\s+you\s+(are|were)|a\s+different)", re.I),
    re.compile(r"\bpretend\s+(you\s+(are|have|don'?t)|there\s+are\s+no)", re.I),
    re.compile(r"\bDAN\b"),  # "Do Anything Now" jailbreak tag
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdev(eloper)?\s+mode\b", re.I),
    re.compile(r"\bunrestricted\s+mode\b", re.I),
    # Repeat / print / reveal system prompt
    re.compile(r"\brepeat\b.{0,30}\b(system\s+prompt|above|instructions?)\b", re.I),
    re.compile(r"\bprint\s+(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\bshow\s+(me\s+)?(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\breveal\s+(your\s+)?(instructions?|system\s+prompt|constraints?)\b", re.I),
    re.compile(r"\bwhat\s+(is|are|were)\s+your\s+(original\s+)?instructions?\b", re.I),
    # "As a [role]" safety-bypass framing
    re.compile(
        r"\bas\s+a\s+(medical\s+student|doctor|nurse|researcher|test|demo)\b.{0,60}(no\s+restrictions?|without\s+guidelines?|pretend)",
        re.I,
    ),
    # Injection delimiter tricks
    re.compile(r"---\s*system\s*:", re.I),
    re.compile(r"\[system\]", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"\bSYSTEM\s+PROMPT\s*:", re.I),
    # Role-flip / "must answer without" commands
    re.compile(
        r"\byou\s+(must|should|will)\s+(now\s+)?(answer|respond|reply)\s+without\s+(restrictions?|guidelines?|rules?)",
        re.I,
    ),
    re.compile(r"\b(must|should|will)\s+now\s+(answer|respond|reply)\s+without\b", re.I),
    re.compile(
        r"\bnow\s+(answer|respond|reply)\s+without\s+(restrictions?|guidelines?|rules?)", re.I
    ),
    re.compile(
        r"\banswer\s+without\s+(any\s+)?(restrictions?|guidelines?|rules?|constraints?)\b", re.I
    ),
    re.compile(r"\bno\s+longer\s+(bound|restricted|constrained|limited)\s+by\b", re.I),
    # Forget-your-X-completely variants
    re.compile(r"\bforget\b.{0,30}\b(instructions?|rules?|context|constraints?|guidelines?)", re.I),
]

# Minimum query length below which we don't bother pattern-matching
_MIN_QUERY_LENGTH = 3

# Maximum query length; anything longer is suspicious
_MAX_QUERY_LENGTH = 1000


def detect_prompt_injection(query: str) -> bool:
    """Return True if the query contains a known prompt-injection or jailbreak pattern.

    This is a fast, deterministic, regex-based heuristic. It runs before any
    retrieval or LLM call to short-circuit adversarial inputs cheaply.

    Args:
        query: The raw user query string.

    Returns:
        True  → injection detected; the request should be refused.
        False → no injection pattern found; safe to proceed.
    """
    if not query or len(query.strip()) < _MIN_QUERY_LENGTH:
        return False

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            logger.warning(
                "Prompt injection detected. Pattern=%r query_prefix=%r",
                pattern.pattern,
                query[:80],
            )
            return True

    return False


def sanitize_query(query: str) -> str:
    """Lightly sanitize the query for safe logging and downstream use.

    Strips leading/trailing whitespace and collapses internal runs of
    whitespace to a single space. Does NOT alter the semantic content of
    legitimate clinical queries.
    """
    return re.sub(r"\s+", " ", query.strip())
