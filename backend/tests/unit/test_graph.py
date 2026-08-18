"""Unit tests for the deterministic chunk graph and disclaimer stripping."""

from backend.app import graph
from backend.app.generation.citations import strip_trailing_disclaimer
from backend.app.models import Chunk, RetrievalResult


def make_chunk(chunk_id: str, section_number: str = "", recommendation_ids: str = "") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=f"text {chunk_id}",
        document_name="NG243",
        doc_id="nice_ng243",
        source_url="https://example.org",
        document_type="guideline",
        publication_year=2024,
        requires_caution=False,
        page_number=1,
        section_number=section_number,
        recommendation_ids=recommendation_ids,
    )


def make_result(chunk: Chunk, rank: int, score: float = 0.8) -> RetrievalResult:
    return RetrievalResult(chunk=chunk, score=score, rank=rank, below_floor=False)


class TestBuildGraph:
    def test_chunks_in_same_top_section_are_linked(self):
        a = make_chunk("a", section_number="1.4.1")
        b = make_chunk("b", section_number="1.4.2")
        c = make_chunk("c", section_number="1.5.1")

        adjacency = graph.build_graph([a, b, c])

        assert "b" in adjacency["a"]
        assert "a" in adjacency["b"]
        assert "c" not in adjacency["a"]

    def test_chunks_sharing_recommendation_are_linked_across_sections(self):
        a = make_chunk("a", section_number="1.1.1", recommendation_ids="1.1.1")
        b = make_chunk("b", section_number="1.9.2", recommendation_ids="1.1.1")

        adjacency = graph.build_graph([a, b])

        assert adjacency["a"] == ["b"]
        assert adjacency["b"] == ["a"]

    def test_unlinked_chunk_has_no_edges(self):
        a = make_chunk("a", section_number="1.1.1")
        b = make_chunk("b", section_number="2.2.2")

        adjacency = graph.build_graph([a, b])

        assert adjacency["a"] == []
        assert adjacency["b"] == []


class TestPickExpansionIds:
    def setup_method(self):
        self.a = make_chunk("a", section_number="1.4.1")
        self.b = make_chunk("b", section_number="1.4.2")
        self.c = make_chunk("c", section_number="1.4.3")
        self.adjacency = graph.build_graph([self.a, self.b, self.c])

    def test_picks_first_unseen_neighbor(self):
        results = [make_result(self.a, 1)]

        picked = graph.pick_expansion_ids(results, self.adjacency, max_extra=1)

        assert picked == ["b"]

    def test_never_picks_already_retrieved_chunks(self):
        results = [make_result(self.a, 1), make_result(self.b, 2)]

        picked = graph.pick_expansion_ids(results, self.adjacency, max_extra=1)

        assert picked == ["c"]

    def test_respects_max_extra_and_empty_graph(self):
        results = [make_result(self.a, 1)]

        assert graph.pick_expansion_ids(results, self.adjacency, max_extra=0) == []
        assert graph.pick_expansion_ids(results, {}, max_extra=3) == []


class TestWrapExpanded:
    def test_expanded_results_rank_after_seeds(self):
        seed = make_result(make_chunk("a"), rank=1, score=0.7)
        extra = make_chunk("b")

        wrapped = graph.wrap_expanded([extra], [seed])

        assert len(wrapped) == 1
        assert wrapped[0].rank == 2
        assert wrapped[0].score == 0.7
        assert wrapped[0].retriever_mode == "graph"
        assert wrapped[0].below_floor is False


class TestStripDisclaimer:
    def test_removes_trailing_disclaimer(self):
        text = (
            "Give 100mg hydrocortisone [Source 1].\n\nDisclaimer: This information is educational."
        )

        assert strip_trailing_disclaimer(text) == "Give 100mg hydrocortisone [Source 1]."

    def test_leaves_clean_answers_untouched(self):
        text = "Give 100mg hydrocortisone [Source 1]."

        assert strip_trailing_disclaimer(text) == text
