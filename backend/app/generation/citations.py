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
    # Find all [Source N] occurrences. Models often append a recommendation id
    # or page hint inside the bracket ("[Source 3, 1.7.1]"), so tolerate any
    # trailing text after the number rather than dropping the citation.
    matches = re.findall(r"\[Source\s*(\d+)[^\]]*\]", text)

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
                citations.append(_to_citation(str_idx, res, "source_marker"))
        except ValueError:
            pass

    return citations


_RECOMMENDATION_MARKER = re.compile(r"\[(\d+(?:\.\d+)+)\]")


def _to_citation(source_id: str, res: RetrievalResult, resolved_by: str) -> dict:
    """Build one citation dict. document / section / page / full text are always present."""
    return {
        "source_id": source_id,
        "document_name": res.chunk.document_name,
        "section_title": res.chunk.section_title or "",
        "section_number": res.chunk.section_number or "",
        "page_number": res.chunk.page_number,
        "source_url": res.chunk.source_url or "",
        "recommendation_ids": res.chunk.recommendation_ids or "",
        "excerpt": _excerpt(res.chunk.text),
        "text": res.chunk.text,
        "score": round(res.score, 4),
        "absolute_relevance": round(res.absolute_relevance, 4),
        "resolved_by": resolved_by,
    }



def extract_recommendation_citations(text: str, sources: Sequence[RetrievalResult]) -> list[dict]:
    """Map bare recommendation markers like [1.8.6] back to the chunks that carry them.

    Models frequently cite the guideline's own numbering instead of [Source N].
    The recommendation ids are indexed per chunk, so this recovers an exact
    document/section/page attribution rather than guessing.
    """
    ids = []
    seen = set()
    for match in _RECOMMENDATION_MARKER.findall(text):
        if match not in seen:
            seen.add(match)
            ids.append(match)
    if not ids:
        return []

    citations = []
    used = set()
    for rec_id in ids:
        for idx, res in enumerate(sources):
            owned = {
                part.strip()
                for part in (res.chunk.recommendation_ids or "").split(",")
                if part.strip()
            }
            if rec_id in owned and idx not in used:
                used.add(idx)
                citations.append(_to_citation(str(idx + 1), res, "recommendation_id"))
                break
    return citations


def resolve_citations(text: str, sources: Sequence[RetrievalResult]) -> list[dict]:
    """Always return citations carrying document, section and page for a grounded answer.

    Three layers, most precise first, so a correctly-grounded answer can never
    reach the UI with no provenance just because the model formatted its
    markers differently:

    1. explicit [Source N] markers
    2. bare guideline recommendation markers such as [1.8.6]
    3. every source the model was shown

    Layer 3 is deliberate: the answer was generated from exactly these chunks,
    so listing them is accurate provenance, and `resolved_by` records that the
    attribution is block-level rather than claim-level.
    """
    if not sources:
        return []

    citations = extract_citations(text, sources)
    if citations:
        return citations

    citations = extract_recommendation_citations(text, sources)
    if citations:
        return citations

    return [_to_citation(str(i + 1), res, "fallback_all_sources") for i, res in enumerate(sources)]


def should_abstain(results: Sequence[RetrievalResult]) -> bool:
    """Determine if we should refuse to answer based on retrieval quality.

    Abstain if there are no results, or if all results are below the relevance floor.
    """
    if not results:
        return True

    # If there's at least one result above the floor, we do not abstain
    return all(r.below_floor for r in results)
