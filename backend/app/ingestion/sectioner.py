"""Section and recommendation detection (FR-010).

NG243 exposes a clean hierarchy: `N.N` section headings, `N.N.N` numbered
recommendations, and bold prose sub-headings between them (research.md D6). The
numbered recommendation is the unit a clinician would cite, so it becomes the atomic
block the chunker must never split.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from backend.app.errors import NoSectionsError
from backend.app.ingestion.cleaner import CleanPage
from backend.app.ingestion.parser import Line

# "1.2 Initial identification and referral"
_SECTION_HEADING = re.compile(r"^(\d+\.\d+)\s+(\S.*)$")
# "1.2.1 Consider adrenal insufficiency in people with..."
_RECOMMENDATION = re.compile(r"^(\d+\.\d+\.\d+)\s+(\S.*)$")
# NG243 typesets the recommendation number on its own line, body text following.
_RECOMMENDATION_BARE = re.compile(r"^(\d+\.\d+\.\d+)\.?$")

# A bold line short enough to be a heading rather than a bold sentence.
_MAX_SUBHEADING_WORDS = 12
# Points a heading must exceed body text by. NG243: body 12.0, sub 16.5, section 21.0.
_HEADING_SIZE_MARGIN = 1.5
# Separates the sub-heading tier (16.5) from the section/back-matter tier
# (21.0-25.5): anything at or above this is titled like a numbered section
# even when it carries no number.
_TOPMATTER_SIZE_MARGIN = 7.0


@dataclass
class Block:
    """An atomic unit of guideline content, attributed to its place in the document."""

    text: str
    page_number: int
    section_number: str
    section_title: str
    subsection_title: str
    recommendation_id: str  # "" for narrative content


def modal_body_size(pages: list[CleanPage]) -> float:
    """The dominant font size in the document — i.e. body text.

    Font size, not boldness, is the reliable heading signal. NG243 bolds inline
    terms and bullet items, so a bold-only test misclassifies list entries as
    sub-headings and shatters the section grouping.
    """
    # Weighted by character count, not line count: body text dominates by volume
    # even where headings happen to occupy a similar number of lines.
    sizes: Counter[float] = Counter()
    for page in pages:
        if page.is_front_matter:
            continue
        for line in page.lines:
            text = line.text.strip()
            if text:
                sizes[round(line.size, 1)] += len(text)

    return sizes.most_common(1)[0][0] if sizes else 12.0


def _is_subheading(line: Line, body_size: float) -> bool:
    text = line.text.strip()
    if not text or text.startswith(("-", "•")):
        return False
    if text.endswith((".", ":", ";", ",")):
        return False
    if len(text.split()) > _MAX_SUBHEADING_WORDS:
        return False
    # Must be visibly larger than body text, and bold.
    return line.bold and line.size >= body_size + _HEADING_SIZE_MARGIN


def _is_topmatter_heading(line: Line, body_size: float) -> bool:
    """True for an unnumbered heading sized like a numbered section heading.

    NG243's back matter -- "Terms used in this guideline", "Rationale and
    impact", "Context", "Update information" -- is typeset at the same 21-25.5pt
    bold tier as numbered `N.N` section headings (research.md D6), well above
    the 16.5pt sub-heading tier. `_SECTION_HEADING` only matches by number, so
    without this check these headings are caught by `_is_subheading` instead
    and every page of glossary/appendix text that follows keeps being stamped
    with the last real section number -- diluting retrieval for every query.
    """
    text = line.text.strip()
    if not text or text.startswith(("-", "•")):
        return False
    if len(text.split()) > _MAX_SUBHEADING_WORDS:
        return False
    return line.bold and line.size >= body_size + _TOPMATTER_SIZE_MARGIN


class _Accumulator:
    """Collects body lines until the next heading or recommendation closes the block."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.page: int | None = None
        self.recommendation_id: str = ""

    def start(self, page: int, recommendation_id: str, first_line: str) -> None:
        self.lines = [first_line]
        self.page = page
        self.recommendation_id = recommendation_id

    def add(self, text: str) -> None:
        if self.page is not None:
            self.lines.append(text)

    @property
    def active(self) -> bool:
        return self.page is not None

    def drain(self) -> tuple[str, int, str] | None:
        if self.page is None:
            return None
        text = " ".join(self.lines).strip()
        result = (text, self.page, self.recommendation_id)
        self.lines, self.page, self.recommendation_id = [], None, ""
        return result if text else None


def detect_blocks(pages: list[CleanPage]) -> list[Block]:
    """Walk the document, emitting one Block per recommendation or narrative run.

    Section and sub-section state carries across page boundaries, because a
    recommendation frequently continues onto the next page.

    Raises:
        NoSectionsError: no numbered structure was found anywhere.
    """
    blocks: list[Block] = []
    section_number = ""
    section_title = ""
    subsection_title = ""
    acc = _Accumulator()
    body_size = modal_body_size(pages)
    # A heading that wraps onto a second line (e.g. "1.9 Managing glucocorticoid
    # withdrawal to prevent" / "adrenal insufficiency") emits that continuation
    # as its own bold, heading-sized line with no number. Without tracking it,
    # the continuation itself was mistaken for a *new* heading -- wiping
    # section_number right back to "" a line after it was correctly set.
    # (kind, font size) of the heading currently allowed to keep wrapping.
    pending_heading: tuple[str, float] | None = None

    def flush() -> None:
        drained = acc.drain()
        if drained is None:
            return
        text, page, rec_id = drained
        blocks.append(
            Block(
                text=text,
                page_number=page,
                section_number=section_number,
                section_title=section_title,
                subsection_title=subsection_title,
                recommendation_id=rec_id,
            )
        )

    for page in pages:
        if page.is_front_matter:
            continue

        for line in page.lines:
            text = line.text.strip()
            if not text:
                continue

            if pending_heading is not None:
                kind, opened_size = pending_heading
                is_continuation = (
                    line.bold
                    and abs(line.size - opened_size) < 0.5
                    and len(text.split()) <= _MAX_SUBHEADING_WORDS
                    and _RECOMMENDATION.match(text) is None
                    and _RECOMMENDATION_BARE.match(text) is None
                    and _SECTION_HEADING.match(text) is None
                )
                if is_continuation:
                    if kind == "sub":
                        subsection_title = f"{subsection_title} {text}".strip()
                    else:
                        section_title = f"{section_title} {text}".strip()
                    continue
                pending_heading = None

            if (match := _RECOMMENDATION.match(text)) is not None:
                flush()
                acc.start(page.page_number, match.group(1), text)
                continue

            # A number alone on its line opens a recommendation whose body follows.
            if (match := _RECOMMENDATION_BARE.match(text)) is not None:
                flush()
                acc.start(page.page_number, match.group(1), match.group(1))
                continue

            if (match := _SECTION_HEADING.match(text)) is not None:
                flush()
                section_number = match.group(1)
                section_title = text
                subsection_title = ""
                pending_heading = ("section", line.size)
                continue

            if _is_topmatter_heading(line, body_size):
                # Unnumbered back matter: leave the numbered section behind.
                # `section_number` is now "" so neither branch below captures
                # its content, and the chunker drops any block that slips
                # through with a blank `section_number` before indexing.
                flush()
                section_number = ""
                section_title = text
                subsection_title = ""
                pending_heading = ("topmatter", line.size)
                continue

            if _is_subheading(line, body_size):
                flush()
                subsection_title = text
                pending_heading = ("sub", line.size)
                continue

            if acc.active:
                acc.add(text)
            elif section_number:
                # Narrative prose under a section, with no recommendation open.
                acc.start(page.page_number, "", text)

    flush()

    if not any(block.section_number for block in blocks):
        raise NoSectionsError(
            "No numbered section hierarchy was detected. Chunks could not be "
            "attributed to a section, so citations would be untrustworthy "
            "(Constitution Principle II)."
        )

    return blocks
