"""SC-006 verified against the real built index (T040, quickstart V8).

The unit tests prove the chunker preserves atomicity on synthetic blocks. This proves
it held on the actual NG243 ingest — the claim that matters for the review gate.
"""

from __future__ import annotations

from collections import Counter

import pytest

from backend.app.retrieval.store import VectorStore


@pytest.fixture(scope="module")
def chunks():
    store = VectorStore()
    if not store.is_ready():
        pytest.skip("No index built. Run: python -m backend.app.cli ingest")
    return store.all_chunks()


def _recommendation_counts(chunks) -> Counter[str]:
    counts: Counter[str] = Counter()
    for chunk in chunks:
        for rec in chunk.recommendation_ids.split(","):
            if rec.strip():
                counts[rec.strip()] += 1
    return counts


class TestRecommendationAtomicity:
    def test_no_recommendation_appears_in_two_chunks(self, chunks):
        """SC-006: zero recommendations split across chunk boundaries."""
        duplicated = {r: n for r, n in _recommendation_counts(chunks).items() if n > 1}
        assert not duplicated, f"recommendations split across chunks: {duplicated}"

    def test_recommendations_were_actually_found(self, chunks):
        """Guards against the test passing vacuously on an empty extraction."""
        assert len(_recommendation_counts(chunks)) >= 50


class TestChunkIntegrity:
    def test_chunk_ids_are_unique(self, chunks):
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_no_chunk_is_empty(self, chunks):
        assert all(c.text.strip() for c in chunks)

    def test_every_chunk_has_a_section(self, chunks):
        assert all(c.section_number for c in chunks)

    def test_oversized_chunks_are_flagged_not_truncated(self, chunks):
        from backend.app.config import get_settings

        ceiling = get_settings().chunk_max_tokens
        for chunk in chunks:
            if chunk.token_count > ceiling:
                assert chunk.is_oversized, (
                    f"{chunk.chunk_id} exceeds the ceiling but is not flagged"
                )

    def test_boilerplate_did_not_survive_into_chunks(self, chunks):
        """The NG243 running footer and rights notice must be gone (FR-005)."""
        for chunk in chunks:
            assert "All rights reserved" not in chunk.text
            assert "Page " not in chunk.text[:10]
