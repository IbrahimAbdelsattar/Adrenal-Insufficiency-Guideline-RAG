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
                continue

            if _is_subheading(line, body_size):
                flush()
                subsection_title = text
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
