"""Cleaning stage (FR-005 through FR-009).

Boilerplate is found by frequency rather than hard-coded strings, so adding a second
source document needs no new code. Every artefact handled here was observed directly
in NG243 (research.md D5).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from backend.app.ingestion.parser import Line, ParsedPage

# Glyphs that PDF extraction mangles out of bullet characters.
_BULLET_GLYPHS = ("�", "", "", "", "•", "●", "▪")

_CONTENTS_LEADER = re.compile(r"\.{4,}\s*\d+\s*$")
_HYPHEN_BREAK = re.compile(r"(\w+)-\n(\w+)")
_SOFT_WRAP = re.compile(r"(?<![\n])\n(?![\n])")
_PAGE_NUMBER_ONLY = re.compile(r"^\s*\d{1,4}\s*$")
# "Page 30 of 63" — per-page text, so frequency detection never catches it.
_PAGE_X_OF_Y = re.compile(r"^Page\s+\d+\s*(of\s*\d*)?\s*$", re.IGNORECASE)
_WHITESPACE_RUN = re.compile(r"[ \t]{2,}")

# Below this, a page has too few lines for frequency analysis to be meaningful.
_MIN_PAGES_FOR_FREQUENCY = 3


@dataclass
class CleanPage:
    page_number: int
    lines: list[Line] = field(default_factory=list)
    is_front_matter: bool = False

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class CleanResult:
    pages: list[CleanPage]
    boilerplate: set[str]
    pages_processed: int
    pages_empty: int


def normalize_glyphs(text: str) -> str:
    """Repair mangled bullets and exotic whitespace (FR-007)."""
    for glyph in _BULLET_GLYPHS:
        text = text.replace(glyph, "- ")
    text = text.replace(" ", " ").replace("‑", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return _WHITESPACE_RUN.sub(" ", text).strip()


def repair_hyphenation(text: str) -> str:
    """Rejoin words split across a line break, then unwrap soft line breaks (FR-006)."""
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    return _SOFT_WRAP.sub(" ", text).strip()


def is_contents_line(text: str) -> bool:
    """A table-of-contents entry, recognisable by its dot leader (FR-008)."""
    return bool(_CONTENTS_LEADER.search(text.strip()))


def find_boilerplate(pages: list[ParsedPage], ratio: float) -> set[str]:
    """Lines appearing on more than `ratio` of pages are running headers/footers."""
    if len(pages) < _MIN_PAGES_FOR_FREQUENCY:
        return set()

    counts: Counter[str] = Counter()
    for page in pages:
        # Count each distinct line once per page, so a repeated in-page phrase
        # is not mistaken for a running header.
        for text in {line.text.strip() for line in page.lines if line.text.strip()}:
            counts[text] += 1

    threshold = max(2, int(len(pages) * ratio))
    return {text for text, count in counts.items() if count >= threshold}


def _is_noise(text: str, boilerplate: set[str]) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped in boilerplate:
        return True
    if _PAGE_NUMBER_ONLY.match(stripped):
        return True
    if _PAGE_X_OF_Y.match(stripped):
        return True
    return is_contents_line(stripped)


def _looks_like_front_matter(lines: list[Line]) -> bool:
    """A page is front matter when it is dominated by contents entries."""
    meaningful = [ln.text.strip() for ln in lines if ln.text.strip()]
    if not meaningful:
        return False
    leaders = sum(1 for t in meaningful if is_contents_line(t))
    return leaders >= max(2, len(meaningful) // 2)


def clean(pages: list[ParsedPage], ratio: float) -> CleanResult:
    """Strip boilerplate and noise, flag front matter, count empty pages."""
    boilerplate = find_boilerplate(pages, ratio)

    cleaned: list[CleanPage] = []
    pages_empty = 0

    for page in pages:
        front_matter = _looks_like_front_matter(page.lines)

        kept: list[Line] = []
        for line in page.lines:
            if _is_noise(line.text, boilerplate):
                continue
            text = normalize_glyphs(line.text)
            if not text:
                continue
            kept.append(Line(text=text, size=line.size, bold=line.bold))

        if not kept:
            pages_empty += 1

        cleaned.append(
            CleanPage(
                page_number=page.page_number,
                lines=kept,
                is_front_matter=front_matter,
            )
        )

    return CleanResult(
        pages=cleaned,
        boilerplate=boilerplate,
        pages_processed=len(pages),
        pages_empty=pages_empty,
    )
