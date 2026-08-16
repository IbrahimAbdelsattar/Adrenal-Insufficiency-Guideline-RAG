"""Unit tests for the cleaning stage (T016, FR-005 through FR-009).

Artefacts under test were observed directly in NICE NG243 (research.md D5).
"""

from __future__ import annotations

from backend.app.ingestion.cleaner import (
    clean,
    find_boilerplate,
    is_contents_line,
    normalize_glyphs,
    repair_hyphenation,
)
from backend.app.ingestion.parser import Line, ParsedPage

FOOTER = "Adrenal insufficiency: identification and management (NG243)"
RIGHTS = "(c) NICE 2026. All rights reserved. Subject to Notice of rights"


def _page(number: int, texts: list[str]) -> ParsedPage:
    return ParsedPage(
        page_number=number,
        lines=[Line(text=t, size=10.0, bold=False) for t in texts],
    )


class TestNormalizeGlyphs:
    def test_replacement_char_becomes_bullet(self):
        assert normalize_glyphs("� weight loss").strip() == "- weight loss"

    def test_private_use_bullet_becomes_bullet(self):
        assert normalize_glyphs(" salt craving").strip() == "- salt craving"

    def test_unicode_bullet_becomes_bullet(self):
        assert normalize_glyphs("• lethargy").strip() == "- lethargy"

    def test_plain_text_is_untouched(self):
        assert normalize_glyphs("hyperkalaemia") == "hyperkalaemia"

    def test_nbsp_becomes_space(self):
        assert normalize_glyphs("early puberty") == "early puberty"


class TestRepairHyphenation:
    def test_rejoins_split_word(self):
        assert repair_hyphenation("hyper-\npigmentation") == "hyperpigmentation"

    def test_preserves_genuine_hyphen(self):
        assert repair_hyphenation("light-headedness") == "light-headedness"

    def test_collapses_soft_wrap_newline_to_space(self):
        assert repair_hyphenation("salt\ncraving") == "salt craving"


class TestContentsDetection:
    def test_dot_leader_line_detected(self):
        assert is_contents_line("Overview ..................................... 5")

    def test_normal_line_not_detected(self):
        assert not is_contents_line("Consider adrenal insufficiency in people with")

    def test_short_dot_run_not_detected(self):
        assert not is_contents_line("e.g. ... and so on")


class TestFindBoilerplate:
    def test_line_on_every_page_is_boilerplate(self):
        pages = [_page(i, [FOOTER, f"unique body text {i}"]) for i in range(1, 11)]
        assert FOOTER in find_boilerplate(pages, ratio=0.6)

    def test_line_below_ratio_is_not_boilerplate(self):
        pages = [_page(i, [f"body {i}"]) for i in range(1, 11)]
        pages[0].lines.append(Line(text="rare line", size=10.0, bold=False))
        assert "rare line" not in find_boilerplate(pages, ratio=0.6)

    def test_unique_body_text_survives(self):
        pages = [_page(i, [FOOTER, f"unique body text {i}"]) for i in range(1, 11)]
        found = find_boilerplate(pages, ratio=0.6)
        assert not any(f.startswith("unique body text") for f in found)


class TestClean:
    def test_boilerplate_removed_from_output(self):
        pages = [
            _page(i, [f"1.2.{i} Consider adrenal insufficiency in people.", FOOTER, RIGHTS])
            for i in range(1, 11)
        ]
        result = clean(pages, ratio=0.6)
        remaining = [ln.text for p in result.pages for ln in p.lines]
        assert FOOTER not in remaining
        assert RIGHTS not in remaining
        assert any("Consider adrenal insufficiency" in t for t in remaining)

    def test_contents_page_flagged_as_front_matter(self):
        pages = [
            _page(1, ["Contents", "Overview ................ 5", "Recommendations ....... 6"]),
            _page(2, ["1.1.1 Follow the recommendations in NICE's guidance."]),
        ]
        result = clean(pages, ratio=0.6)
        assert result.pages[0].is_front_matter
        assert not result.pages[1].is_front_matter

    def test_empty_pages_are_counted(self):
        pages = [_page(i, [FOOTER]) for i in range(1, 11)]
        result = clean(pages, ratio=0.6)
        assert result.pages_empty == 10

    def test_pages_processed_reported(self):
        pages = [_page(i, [f"body {i}"]) for i in range(1, 6)]
        assert clean(pages, ratio=0.6).pages_processed == 5
