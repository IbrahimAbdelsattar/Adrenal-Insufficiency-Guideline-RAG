"""PDF text extraction with PyMuPDF (FR-004, research.md D4).

Extraction is span-level so font size and weight survive into the sectioner — that
metadata is what lets headings be detected without a layout model. Page numbers are
1-indexed and correspond to the real PDF page, so a human can always trace a chunk
back to the page it came from (Constitution Principle VI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from backend.app.errors import NoTextLayerError

# A span is treated as bold if its font name says so or its weight flag is set.
_BOLD_FLAG = 1 << 4


@dataclass
class Line:
    """One visual line of text with the typographic signal we need downstream."""

    text: str
    size: float
    bold: bool


@dataclass
class ParsedPage:
    page_number: int  # 1-indexed, matches the PDF
    lines: list[Line] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(line.text.strip() for line in self.lines)


def _line_from_spans(spans: list[dict]) -> Line | None:
    text = "".join(span.get("text", "") for span in spans).strip()
    if not text:
        return None

    sizes = [float(span.get("size", 0)) for span in spans] or [0.0]
    bold = any(
        bool(int(span.get("flags", 0)) & _BOLD_FLAG)
        or "bold" in str(span.get("font", "")).lower()
        for span in spans
    )
    return Line(text=text, size=max(sizes), bold=bold)


def parse_pdf(path: Path) -> list[ParsedPage]:
    """Extract every page as a list of lines.

    Raises:
        NoTextLayerError: the document yielded no text at all (likely scanned).
    """
    pages: list[ParsedPage] = []

    with pymupdf.open(path) as document:
        for index, page in enumerate(document, start=1):
            parsed = ParsedPage(page_number=index)
            content = page.get_text("dict")

            for block in content.get("blocks", []):
                # type 0 == text block; images and drawings are ignored.
                if block.get("type") != 0:
                    continue
                for raw_line in block.get("lines", []):
                    line = _line_from_spans(raw_line.get("spans", []))
                    if line is not None:
                        parsed.lines.append(line)

            pages.append(parsed)

    if not any(not page.is_empty for page in pages):
        raise NoTextLayerError(
            f"{path.name} contains no extractable text. It is probably a scanned "
            "document; OCR is out of scope for this feature."
        )

    return pages
