"""Lightweight deterministic knowledge graph over indexed chunks.

Instead of LLM-built GraphRAG (expensive to index and query), the graph is
derived for free from structure the ingestion pipeline already extracts:

- chunks sharing a top-level guideline section (e.g. 1.4) are siblings
- chunks citing the same numbered recommendation are linked

At query time the top-k evidence is expanded with one linked chunk, giving
the generator adjacent context (e.g. crisis dosing next to sick-day rules)
at the cost of a single extra evidence block.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from backend.app.models import Chunk, RetrievalResult

logger = logging.getLogger(__name__)

GRAPH_FILENAME = "graph.json"

# adjacency chunk_id -> linked chunk_ids, plus mtime for cache invalidation
_GRAPH_CACHE: dict[str, tuple[float, dict[str, list[str]]]] = {}


def _top_section(section_number: str) -> str:
    parts = section_number.strip().split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else section_number.strip()


def _recommendation_ids(chunk: Chunk) -> list[str]:
    raw = chunk.recommendation_ids.replace(";", ",")
    return [r.strip() for r in raw.split(",") if r.strip()]


def build_graph(chunks: Sequence[Chunk]) -> dict[str, list[str]]:
    """Deterministic adjacency map: chunk_id -> linked chunk_ids."""
    by_section: dict[str, list[str]] = {}
    by_recommendation: dict[str, list[str]] = {}

    for chunk in chunks:
        if chunk.section_number:
            by_section.setdefault(_top_section(chunk.section_number), []).append(chunk.chunk_id)
        for rec_id in _recommendation_ids(chunk):
            by_recommendation.setdefault(rec_id, []).append(chunk.chunk_id)

    adjacency: dict[str, set[str]] = {}
    for group in [*by_section.values(), *by_recommendation.values()]:
        for chunk_id in group:
            adjacency.setdefault(chunk_id, set()).update(
                other for other in group if other != chunk_id
            )

    return {cid: sorted(neighbors) for cid, neighbors in adjacency.items()}


def edge_count(adjacency: dict[str, list[str]]) -> int:
    return sum(len(v) for v in adjacency.values()) // 2


def save_graph(adjacency: dict[str, list[str]], index_dir: Path) -> Path:
    path = index_dir / GRAPH_FILENAME
    path.write_text(json.dumps(adjacency, indent=1), encoding="utf-8")
    return path


def load_graph(index_dir: Path) -> dict[str, list[str]]:
    """Load graph.json with an mtime-validated module cache."""
    path = index_dir / GRAPH_FILENAME
    if not path.exists():
        return {}

    mtime = path.stat().st_mtime
    cached = _GRAPH_CACHE.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        adjacency = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load graph %s: %s", path, exc)
        return {}

    _GRAPH_CACHE[str(path)] = (mtime, adjacency)
    return adjacency


def pick_expansion_ids(
    results: Sequence[RetrievalResult],
    adjacency: dict[str, list[str]],
    max_extra: int,
) -> list[str]:
    """Choose up to max_extra chunk IDs linked to the retrieved evidence."""
    if max_extra <= 0 or not adjacency:
        return []

    present = {r.chunk.chunk_id for r in results}
    picked: list[str] = []

    for result in results:
        for neighbor in adjacency.get(result.chunk.chunk_id, []):
            if neighbor not in present and neighbor not in picked:
                picked.append(neighbor)
                break
        if len(picked) >= max_extra:
            break

    return picked


def wrap_expanded(
    chunks: Sequence[Chunk],
    seed_results: Sequence[RetrievalResult],
) -> list[RetrievalResult]:
    """Wrap graph-expanded chunks as RetrievalResults ranked after the seeds."""
    floor_score = min((r.score for r in seed_results), default=0.0)
    next_rank = len(seed_results) + 1
    return [
        RetrievalResult(
            chunk=chunk,
            score=floor_score,
            rank=next_rank + i,
            below_floor=False,
            retriever_mode="graph",
        )
        for i, chunk in enumerate(chunks)
    ]
