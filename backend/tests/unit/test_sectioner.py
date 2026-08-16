"""Unit tests for section and recommendation detection (T017, FR-010).

Fixture text mirrors the real NG243 shape: `N.N` section headings, `N.N.N` numbered
recommendations, and prose sub-headings nested between them.
"""

from __future__ import annotations

import pytest

from backend.app.errors import NoSectionsError
from backend.app.ingestion.cleaner import CleanPage
from backend.app.ingestion.parser import Line
from backend.app.ingestion.sectioner import detect_blocks


# Real NG243 typography: body 12.0pt, sub-headings 16.5pt, section headings 21.0pt.
BODY_SIZE = 12.0
HEADING_SIZE = 16.5


def _clean_page(number: int, entries: list[tuple[str, bool]]) -> CleanPage:
    """entries: (text, is_heading). Headings are bold AND larger than body text."""
    return CleanPage(
        page_number=number,
        lines=[
            Line(text=t, size=HEADING_SIZE if h else BODY_SIZE, bold=h)
            for t, h in entries
        ],
        is_front_matter=False,
    )


NG243_PAGE_6 = _clean_page(
    6,
    [
        ("1.1 Information, support and decision making", True),
        ("1.1.1 For advice on communicating with people with adrenal insufficiency,", False),
        ("follow the recommendations in NICE's guideline on patient experience.", False),
        ("1.1.2 When making decisions with people who have learning disabilities,", False),
        ("follow the recommendations in NICE's guideline on shared decision making.", False),
    ],
)

NG243_PAGE_9 = _clean_page(
    9,
    [
        ("1.2 Initial identification and referral", True),
        ("When to suspect adrenal insufficiency", True),
        ("1.2.1 Consider adrenal insufficiency in people with unexplained", False),
        ("hyperpigmentation, or when there is no other clinical explanation.", False),
    ],
)


class TestSectionDetection:
    def test_numbered_section_heading_detected(self):
        blocks = detect_blocks([NG243_PAGE_6])
        assert all(b.section_number == "1.1" for b in blocks)
        assert all(
            b.section_title == "1.1 Information, support and decision making"
            for b in blocks
        )

    def test_recommendations_split_into_separate_blocks(self):
        blocks = detect_blocks([NG243_PAGE_6])
        ids = [b.recommendation_id for b in blocks if b.recommendation_id]
        assert ids == ["1.1.1", "1.1.2"]

    def test_recommendation_body_lines_are_joined(self):
        blocks = detect_blocks([NG243_PAGE_6])
        first = next(b for b in blocks if b.recommendation_id == "1.1.1")
        assert "patient experience" in first.text
        assert "communicating with people" in first.text

    def test_prose_subheading_captured(self):
        blocks = detect_blocks([NG243_PAGE_9])
        rec = next(b for b in blocks if b.recommendation_id == "1.2.1")
        assert rec.subsection_title == "When to suspect adrenal insufficiency"

    def test_page_number_preserved(self):
        blocks = detect_blocks([NG243_PAGE_9])
        assert all(b.page_number == 9 for b in blocks)


class TestBareNumberRecommendations:
    """NG243 typesets the recommendation number on its own line (observed on p.9)."""

    BARE = _clean_page(
        9,
        [
            ("1.2 Initial identification and referral", True),
            ("When to suspect adrenal insufficiency", True),
            ("1.2.1", False),
            ("Consider adrenal insufficiency in people with unexplained", False),
            ("hyperpigmentation, or when there is no other explanation.", False),
            ("1.2.2", False),
            ("Refer people with suspected adrenal insufficiency urgently.", False),
        ],
    )

    def test_bare_number_opens_a_recommendation(self):
        blocks = detect_blocks([self.BARE])
        ids = [b.recommendation_id for b in blocks if b.recommendation_id]
        assert ids == ["1.2.1", "1.2.2"]

    def test_following_lines_become_the_body(self):
        blocks = detect_blocks([self.BARE])
        first = next(b for b in blocks if b.recommendation_id == "1.2.1")
        assert "Consider adrenal insufficiency" in first.text
        assert "hyperpigmentation" in first.text

    def test_body_stops_at_the_next_number(self):
        blocks = detect_blocks([self.BARE])
        first = next(b for b in blocks if b.recommendation_id == "1.2.1")
        assert "Refer people" not in first.text

    def test_bare_number_is_not_emitted_as_its_own_tiny_block(self):
        blocks = detect_blocks([self.BARE])
        assert all(len(b.text.strip()) > 8 for b in blocks)


class TestSectionStateAcrossPages:
    def test_section_carries_to_next_page(self):
        continuation = _clean_page(
            7, [("1.1.3 Follow NICE's guideline on babies and young people.", False)]
        )
        blocks = detect_blocks([NG243_PAGE_6, continuation])
        last = blocks[-1]
        assert last.recommendation_id == "1.1.3"
        assert last.section_number == "1.1"
        assert last.page_number == 7

    def test_new_section_resets_subsection(self):
        blocks = detect_blocks([NG243_PAGE_9, NG243_PAGE_6])
        later = next(b for b in blocks if b.recommendation_id == "1.1.1")
        assert later.subsection_title == ""


class TestFailureModes:
    def test_front_matter_pages_are_skipped(self):
        front = _clean_page(1, [("Adrenal insufficiency", True)])
        front.is_front_matter = True
        blocks = detect_blocks([front, NG243_PAGE_6])
        assert all(b.page_number != 1 for b in blocks)

    def test_no_sections_raises(self):
        blank = _clean_page(1, [("just some prose with no numbering at all", False)])
        with pytest.raises(NoSectionsError):
            detect_blocks([blank])
