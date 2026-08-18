"""Assembles retrieved chunks into a structured evidence context for the LLM."""

from collections.abc import Sequence

from backend.app.models import RetrievalResult


def assemble_evidence(results: Sequence[RetrievalResult]) -> str:
    """Convert retrieval results into numbered evidence blocks with citation metadata.

    Filters out below_floor results if there are any results above floor.
    Otherwise, uses the below_floor results to allow the LLM to explain why
    the evidence is insufficient.
    """
    if not results:
        return "No relevant evidence found."

    valid_results = [r for r in results if not r.below_floor]

    # If everything is below floor, we still provide them so the LLM can
    # analyze them and confidently state that the specific answer is missing.
    sources = valid_results if valid_results else list(results)

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
