"""Removal of model chain-of-thought from generated answers.

Reasoning models (the `n8n-content` / `auto/*` combo routes among them) emit
their scratchpad inline in the completion content, wrapped in `<think>` tags.
That text must never reach a clinician: it is not an answer, and it discusses
sources the model then rejects, so scraping citations from it attributes
guidance to pages the model deliberately ruled out.

Two entry points:

    strip_reasoning   whole-completion cleanup, used for the final answer
    ReasoningFilter   incremental cleanup, used to gate SSE token events
"""

from __future__ import annotations

import re

# Tag names seen in the wild across reasoning models.
_TAGS = ("think", "thinking", "reasoning")
_NAMES = "|".join(_TAGS)

_REASONING_BLOCK = re.compile(rf"<({_NAMES})\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
# An unterminated opener means generation hit max_tokens mid-thought, so
# everything from it onward is reasoning and no answer follows it.
_UNTERMINATED = re.compile(rf"<({_NAMES})\b[^>]*>.*$", re.IGNORECASE | re.DOTALL)

_OPEN_TAG = re.compile(rf"<({_NAMES})\b[^>]*>", re.IGNORECASE)
_CLOSE_TAG = re.compile(rf"</({_NAMES})\s*>", re.IGNORECASE)

# Longest partial opening tag we might have to hold back across chunks,
# e.g. "<reasoning" split mid-token. "+2" covers the "<" and a trailing space.
_MAX_PARTIAL = max(len(t) for t in _TAGS) + len("</") + 2


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought blocks from a complete model output.

    Handles closed blocks and an unterminated opener left by a truncated
    completion. Returns "" when the output was reasoning only -- callers must
    treat that as "no answer produced" and never render it.
    """
    cleaned = _REASONING_BLOCK.sub("", text)
    cleaned = _UNTERMINATED.sub("", cleaned)
    return cleaned.strip()


class ReasoningFilter:
    """Incrementally strips reasoning from a token stream.

    Tags can be split across SSE deltas, so a tail that could still grow into
    an opening tag is held back until the next delta resolves it. Feed every
    delta; emit only what comes back.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, delta: str) -> str:
        """Return the portion of `delta` that is safe to show the user."""
        self._buf += delta
        out: list[str] = []

        while self._buf:
            if self._inside:
                match = _CLOSE_TAG.search(self._buf)
                if not match:
                    # Still thinking. Keep only a possible partial close tag.
                    self._buf = self._buf[-_MAX_PARTIAL:]
                    break
                self._buf = self._buf[match.end() :]
                self._inside = False
                continue

            match = _OPEN_TAG.search(self._buf)
            if match:
                out.append(self._buf[: match.start()])
                self._buf = self._buf[match.end() :]
                self._inside = True
                continue

            # No complete opening tag. Emit everything except a tail that
            # might still become one.
            cut = max(0, len(self._buf) - _MAX_PARTIAL)
            safe, tail = self._buf[:cut], self._buf[cut:]
            if "<" in tail:
                # Emit up to the last "<"; it may start a tag.
                idx = tail.rindex("<")
                safe += tail[:idx]
                tail = tail[idx:]
            out.append(safe)
            self._buf = tail
            break

        return "".join(out)

    def flush(self) -> str:
        """Return any held-back text once the stream has ended."""
        if self._inside:
            self._buf = ""
            return ""
        remainder, self._buf = self._buf, ""
        return remainder
