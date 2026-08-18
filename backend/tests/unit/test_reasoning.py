"""Regression tests for chain-of-thought removal.

A reasoning model returned a `<think>` block that consumed the whole token
budget. The block was rendered to the clinician as if it were the answer, and
citations were scraped out of it -- attributing guidance to pages the model had
explicitly rejected inside that same reasoning.
"""

import pytest

from backend.app.generation.reasoning import ReasoningFilter, strip_reasoning


class TestStripReasoning:
    def test_removes_closed_block_and_keeps_answer(self):
        raw = "<think>Source 4 is about tapering, not crises.</think>\nGive hydrocortisone [Source 1]."
        assert strip_reasoning(raw) == "Give hydrocortisone [Source 1]."

    def test_unterminated_block_yields_nothing(self):
        """Truncated at max_tokens mid-thought: there is no answer to show."""
        assert strip_reasoning("<think>Still planning, cite [Source 5] maybe") == ""

    def test_plain_answer_is_untouched(self):
        assert strip_reasoning("Give 1 litre of 0.9% saline [Source 2].") == (
            "Give 1 litre of 0.9% saline [Source 2]."
        )

    @pytest.mark.parametrize("tag", ["think", "thinking", "reasoning", "THINK"])
    def test_handles_tag_variants(self, tag):
        assert strip_reasoning(f"<{tag}>hidden</{tag}>Answer") == "Answer"

    def test_does_not_eat_ordinary_markup(self):
        assert strip_reasoning("A <b>bold</b> claim") == "A <b>bold</b> claim"

    def test_reasoning_citations_are_not_extractable_after_stripping(self):
        """The whole point: rejected sources must not survive into citations."""
        raw = "<think>[Source 4] and [Source 5] are irrelevant.</think>Use [Source 1]."
        cleaned = strip_reasoning(raw)
        assert "[Source 4]" not in cleaned
        assert "[Source 5]" not in cleaned
        assert "[Source 1]" in cleaned


class TestReasoningFilter:
    @staticmethod
    def _run(chunks):
        f = ReasoningFilter()
        return "".join([f.feed(c) for c in chunks] + [f.flush()])

    def test_suppresses_reasoning_across_stream(self):
        assert self._run(["<think>", "plan", "</think>", "Answer."]) == "Answer."

    def test_tag_split_across_deltas(self):
        """SSE deltas cut tags in half; a partial tag must be held back."""
        assert self._run(["<thi", "nk>secret", "</thi", "nk>Visible"]) == "Visible"

    def test_never_emits_when_block_never_closes(self):
        assert self._run(["<think>unfinished reasoning"]) == ""

    def test_text_before_and_after_block_survives(self):
        assert self._run(["Intro ", "<think>x</think>", " Outro"]) == "Intro  Outro"

    def test_passes_through_when_no_reasoning(self):
        assert self._run(["Give ", "hydrocortisone ", "[Source 1]."]) == (
            "Give hydrocortisone [Source 1]."
        )
