"""Unit tests for clarifying-question suggestions on ambiguously-scoped queries."""

from backend.app.generation.clarification import suggest_clarifying_questions


def test_ambiguous_dosing_query_asks_both_questions():
    questions = suggest_clarifying_questions("What is the hydrocortisone dose?")
    assert len(questions) == 2
    assert any("adult" in q.lower() for q in questions)
    assert any("routine" in q.lower() or "emergency" in q.lower() for q in questions)


def test_fully_scoped_query_asks_nothing():
    questions = suggest_clarifying_questions(
        "What is the hydrocortisone dose for adults in adrenal crisis?"
    )
    assert questions == []


def test_only_missing_age_group_asks_one_question():
    questions = suggest_clarifying_questions("Give me the emergency hydrocortisone dose.")
    assert len(questions) == 1
    assert "adult" in questions[0].lower()


def test_non_dosing_query_is_never_flagged():
    """Ambiguity elsewhere (diagnosis, symptoms) doesn't risk steering a dose."""
    assert suggest_clarifying_questions("What are the symptoms of adrenal insufficiency?") == []


def test_empty_query_returns_nothing():
    assert suggest_clarifying_questions("") == []


def test_query_quoting_the_guideline_is_not_flagged():
    """Evidence already carries whatever scoping it needed."""
    questions = suggest_clarifying_questions("Explain [Source 1] hydrocortisone dosing further.")
    assert questions == []
