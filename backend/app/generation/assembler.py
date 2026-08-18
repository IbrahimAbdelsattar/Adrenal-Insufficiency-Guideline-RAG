"""Assembles retrieved chunks into a structured evidence context for the LLM."""

from collections.abc import Sequence

from backend.app.models import RetrievalResult


def select_sources(results: Sequence[RetrievalResult]) -> list[RetrievalResult]:
    """Pick the exact chunks that become [Source 1..N], in that order.

    Drops below_floor results when anything is above the floor; if everything
    is below, keeps them so the LLM can state that the answer is missing.

    Callers MUST number citations against this list, not the raw results:
    `[Source N]` is a 1-based index into it, so assembling from one list and
    resolving citations from another silently attributes text to the wrong page.
    """
    if not results:
        return []
    above_floor = [r for r in results if not r.below_floor]
    return above_floor if above_floor else list(results)


def assemble_evidence(results: Sequence[RetrievalResult]) -> str:
    """Convert retrieval results into numbered evidence blocks with citation metadata.

    Numbering follows `select_sources(results)`; pass that same list to
    `extract_citations` so [Source N] resolves to the chunk the LLM was shown.
    """
    if not results:
        return "No relevant evidence found."

    sources = select_sources(results)

    blocks = []
    for i, res in enumerate(sources, start=1):
        chunk = res.chunk

        meta_lines = []
        meta_lines.append(f"Document: {chunk.document_name}")

        if chunk.section_number or chunk.section_title:
            sec = chunk.section_number or ""
            if chunk.section_title:
                sec += f" {chunk.section_title}" if sec else chunk.section_title
            meta_lines.append(f"Section: {sec.strip()}")

        if chunk.recommendation_ids:
            meta_lines.append(f"Recommendations: {chunk.recommendation_ids}")

        meta_lines.append(f"Page: {chunk.page_number}")
        if chunk.requires_caution:
            meta_lines.append(
                "CAUTION: This document requires caution (may be outdated or non-guideline)."
            )

        header = f"[Source {i}]"
        meta = "\n".join(meta_lines)
        blocks.append(f"{header}\n{meta}\n---\n{chunk.text}\n")

    return "\n".join(blocks)
