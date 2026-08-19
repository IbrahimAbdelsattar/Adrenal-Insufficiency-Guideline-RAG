"""Extracts citations from LLM output and validates that clinical claims are grounded."""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

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
    """Build one citation dict. document / section / page / full text are always present.

    `resolved_by` is what the UI must use to distinguish an explicit claim
    citation ("source_marker": the model wrote `[Source N]` right next to this
    claim) from an indirect one ("recommendation_id": the model cited the
    guideline's own numbering, which was resolved back to a chunk but was
    never validated against a specific sentence). `score` is retrieval
    ranking only -- callers must label it "retrieval score", never "clinical
    confidence"; it says how well the chunk matched the query, not whether
    the claim built from it is correct.
    """
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
        "below_floor": res.below_floor,
        "publication_year": res.chunk.publication_year,
        "document_type": res.chunk.document_type,
        "requires_caution": res.chunk.requires_caution,
        # When this citation was resolved, not when the guideline was
        # published -- lets the UI show "retrieved just now" vs. a stale
        # cached answer being replayed. `publication_year` above is the
        # closest honest proxy for a "source version" this corpus has; the
        # ingestion pipeline does not track guideline revision numbers.
        "retrieved_at": datetime.now(UTC).isoformat(),
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
    """Return only citations the model actually pointed at, most precise first.

    1. explicit [Source N] markers
    2. bare guideline recommendation markers such as [1.8.6]

    No fallback layer. Earlier this fell back to attaching every source the
    model was shown when neither format was found -- that proves evidence was
    *retrieved*, not that any specific claim in the answer is *supported* by
    it, and let an ungrounded answer reach the clinician wearing a citation
    list it never earned. An answer with no resolvable citation now returns
    an empty list; callers must treat that as ungrounded (see
    `validate_grounding`), not silently attribute it to everything retrieved.
    """
    if not sources:
        return []

    citations = extract_citations(text, sources)
    if citations:
        return citations

    return extract_recommendation_citations(text, sources)


_SOURCE_MARKER = re.compile(r"\[Source\s*(\d+)[^\]]*\]", re.IGNORECASE)

# Claim shapes that must never reach a clinician unsupported: doses, routes,
# timing/frequency, lab or vital thresholds, and emergency instructions. Kept
# as one alternation so a single scan over a claim unit answers "does this
# look clinical" -- deliberately over-inclusive (a false positive just asks
# for a citation that harmlessly exists), never under-inclusive.
#
# Deliberately excludes bare "emergency" / "adrenal crisis" -- this app's
# entire domain is adrenal crisis, so those words appear in ordinary framing
# prose ("Immediate Emergency Administration", "management of adrenal
# crisis involves...") far more often than in an actual instruction. Only
# the specific actionable phrasings below count as emergency-instruction
# claims; a topic mention with no numeric/route/timing content needs no
# citation of its own.
_CLINICAL_CLAIM_PATTERN = re.compile(
    r"""
    \d+(?:\.\d+)?\s*(?:mg|mcg|microgram\w*|milligram\w*|g|ml|iu|units?|mmol|nmol)\b # dose / units
    | \b(?:intravenous(?:ly)?|intramuscular(?:ly)?|subcutaneous(?:ly)?|orally|by\ mouth|\biv\b|\bim\b|\bsc\b)\b # route
    | \bevery\s+\d+\s*(?:hour|hr|minute|min|day|week)s?\b   # dosing frequency
    | \bwithin\s+\d+\s*(?:hour|hr|minute|min)s?\b           # timing
    | \bimmediately\b | \burgently\b | \bwithout\ delay\b   # timing / urgency
    | [<>≤≥]\s*\d+                                          # threshold comparison
    | \b\d+\s*(?:nmol/l|mmol/l|mg/dl|mmhg|bpm|%)\b           # lab / vital threshold
    | \bcall\ (?:999|911|112|an\ ambulance)\b               # emergency instruction
    | \bseek\ (?:immediate|urgent)\ medical\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A markdown/organizational heading, not a claim: "### 1. Immediate Emergency
# Administration", "**Route:**", "1. Ongoing Parenteral Dosing". Headings
# routinely contain trigger words ("Emergency", "Dosing") without making any
# claim themselves -- the claim is in the content underneath, which is
# checked on its own. Matched against a whole line, before any sentence split.
_HEADING_LINE = re.compile(
    r"^#{1,6}\s+\S"  # ATX heading: ### Title
    r"|^\*{1,2}[^*\n]+\*{1,2}:?\s*$"  # **Bold label** on its own line
    r"|^\*{0,2}\d+\.\s+[A-Z][^.!?]{0,80}$"  # 1. Short Title Case Heading
)

# Splits one line into claim-sized sentences. Good enough to flag an uncited
# clinical sentence; it is not a clause-level parser.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")


def _split_claim_units(text: str) -> list[str]:
    """Break an answer into claim-sized units, skipping heading lines.

    Splits on lines first so a heading can be recognised and excluded before
    any sentence-boundary heuristics run on it; each remaining line is then
    split into sentences, since a single bullet can carry more than one claim.
    """
    units = []
    for line in text.split("\n"):
        line = line.strip().lstrip("*-•").strip()
        if not line or _HEADING_LINE.match(line):
            continue
        units.extend(u.strip() for u in _SENTENCE_SPLIT.split(line) if u.strip())
    return units


def _marker_validity(text: str, n_sources: int) -> tuple[list[str], list[str]]:
    """Every [Source N] marker in *text*, split into (valid, out-of-range) ids."""
    valid, invalid = [], []
    for raw in _SOURCE_MARKER.findall(text):
        idx = int(raw)
        (valid if 1 <= idx <= n_sources else invalid).append(raw)
    return valid, invalid


@dataclass
class GroundingResult:
    """Outcome of validating that an answer's clinical claims are cited.

    `status` is the contract callers must act on:

    - "verified": every clinical claim resolves to a real [Source N] (or a
      resolvable bare recommendation marker); `citations` is safe to show and
      to cache.
    - "failed": either an out-of-range/invalid marker was used, or at least
      one clinical claim (dose, route, timing, threshold, emergency
      instruction) has no citation at all. `citations` is always empty --
      callers must abstain, not display a partial answer.
    """

    status: Literal["verified", "failed"]
    citations: list[dict] = field(default_factory=list)
    reason: str = ""
    invalid_markers: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)


def validate_grounding(text: str, sources: Sequence[RetrievalResult]) -> GroundingResult:
    """Reject an answer unless every clinical claim in it is actually cited.

    Two failure modes, checked in order:

    1. Any [Source N] marker pointing outside 1..len(sources) -- the model
       cited evidence that was never shown to it, so nothing it says about
       that citation can be trusted.
    2. Any individual claim unit (line or sentence) matching a clinical claim
       shape -- dose, route, timing, threshold, emergency instruction -- that
       carries no citation of its own. A citation elsewhere in the answer
       does not cover it; this is deliberately per-claim, not per-answer,
       because "the answer has a citation somewhere" is exactly the weak
       check that let ungrounded claims through before.

    An answer with no clinical claims at all (e.g. a plain restatement of
    what the evidence does not cover) needs no citation to be "verified" --
    there is nothing in it that requires provenance.
    """
    n = len(sources)
    if n == 0:
        return GroundingResult(status="failed", reason="no_sources")

    _, invalid = _marker_validity(text, n)
    if invalid:
        return GroundingResult(
            status="failed",
            reason="invalid_citation_marker",
            invalid_markers=sorted(set(invalid)),
        )

    unsupported = []
    for line in text.split("\n"):
        line = line.strip().lstrip("*-•").strip()
        if not line or _HEADING_LINE.match(line):
            continue
        # If the line contains a valid citation or recommendation marker, claims in this block are grounded
        line_valid, _ = _marker_validity(line, n)
        if line_valid or _RECOMMENDATION_MARKER.search(line):
            continue

        # If the line has no citation marker at all, check if any sentence makes an uncited clinical claim
        for unit in _SENTENCE_SPLIT.split(line):
            unit = unit.strip()
            if not unit:
                continue
            if _CLINICAL_CLAIM_PATTERN.search(unit):
                unsupported.append(unit[:160])

    if unsupported:
        return GroundingResult(
            status="failed",
            reason="unsupported_clinical_claim",
            unsupported_claims=unsupported,
        )


    citations = resolve_citations(text, sources)
    return GroundingResult(status="verified", citations=citations)


def should_abstain(results: Sequence[RetrievalResult]) -> bool:
    """Determine if we should refuse to answer based on retrieval quality.

    Abstain if there are no results, or if all results are below the relevance floor.
    """
    if not results:
        return True

    # If there's at least one result above the floor, we do not abstain
    return all(r.below_floor for r in results)
