"""Extracts citations from LLM output and maps them to retrieved sources."""
import re
from typing import Sequence

from backend.app.models import RetrievalResult


def extract_citations(text: str, sources: Sequence[RetrievalResult]) -> list[dict]:
    """Find [Source N] markers in text and map them to the corresponding chunks.
    
    Returns a deduplicated list of citation dicts containing metadata for the UI.
    """
    # Find all [Source N] occurrences
    matches = re.findall(r"\[Source (\d+)\]", text)
    
    # Deduplicate while preserving order of appearance
    seen = set()
    unique_ids = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_ids.append(m)
            
    citations = []
    for str_idx in unique_ids:
        try:
            idx = int(str_idx) - 1
            if 0 <= idx < len(sources):
                res = sources[idx]
                citations.append({
                    "source_id": str_idx,
                    "document_name": res.chunk.document_name,
                    "section_title": res.chunk.section_title or "",
                    "section_number": res.chunk.section_number or "",
                    "page_number": res.chunk.page_number,
                    "source_url": res.chunk.source_url or "",
                })
        except ValueError:
            pass
            
    return citations


def should_abstain(results: Sequence[RetrievalResult]) -> bool:
    """Determine if we should refuse to answer based on retrieval quality.
    
    Abstain if there are no results, or if all results are below the relevance floor.
    """
    if not results:
        return True
        
    # If there's at least one result above the floor, we do not abstain
    return all(r.below_floor for r in results)
