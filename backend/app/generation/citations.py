"""Extracts citations from LLM output and maps them to retrieved sources."""

import re
from collections.abc import Sequence

from backend.app.models import RetrievalResult

_TRAILING_DISCLAIMER = re.compile(
    r"\n+\s*(?:\*\*)?disclaimer(?:\*\*)?:.*$", re.IGNORECASE | re.DOTALL
)

# Constitution Principle II: citation metadata is structural, not cosmetic.
# An excerpt this long is enough for a human to recognise the source passage
# without reproducing the full chunk in the API response.
_EXCERPT_MAX_CHARS = 240


def _excerpt(text: str, max_chars: int = _EXCERPT_MAX_CHARS) -> str:
    """First `max_chars` of the chunk text, cut on a word boundary."""
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    cut = clean.rfind(" ", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    return clean[:cut].rstrip() + "…"


def strip_trailing_disclaimer(text: str) -> str:
    """Remove a trailing disclaimer block; the API appends its own."""
    return _TRAILING_DISCLAIMER.sub("", text).rstrip()


def extract_citations(text: str, sources: Sequence[RetrievalResult]) -> list[dict]:
    """Find [Source N] markers in text and map them to the corresponding chunks.

    Returns a deduplicated list of citation dicts containing metadata for the UI.
    """
    # Find all [Source N] occurrences
    matches = re.findall(r"\[Source (\d+)\]", text)

    # Deduplicate while preserving order of appearance
    seen = set()
    unique_ids = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_ids.append(m)

    citations = []
    for str_idx in unique_ids:
        try:
            idx = int(str_idx) - 1
            if 0 <= idx < len(sources):
                res = sources[idx]
                citations.append(
                    {
                        "source_id": str_idx,
                        "document_name": res.chunk.document_name,
                        "section_title": res.chunk.section_title or "",
                        "section_number": res.chunk.section_number or "",
                        "page_number": res.chunk.page_number,
                        "source_url": res.chunk.source_url or "",
                        "recommendation_ids": res.chunk.recommendation_ids or "",
                        "excerpt": _excerpt(res.chunk.text),
                    }
                )
        except ValueError:
            pass

    return citations


def should_abstain(results: Sequence[RetrievalResult]) -> bool:
    """Determine if we should refuse to answer based on retrieval quality.

    Abstain if there are no results, or if all results are below the relevance floor.
    """
    if not results:
        return True

    # If there's at least one result above the floor, we do not abstain
    return all(r.below_floor for r in results)
