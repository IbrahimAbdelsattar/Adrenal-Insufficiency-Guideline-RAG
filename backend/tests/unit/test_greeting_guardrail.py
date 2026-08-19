from backend.app.generation.guardrails import GREETING_RESPONSE_EN, is_greeting


def test_capability_questions_are_handled_before_retrieval() -> None:
    assert is_greeting("how can you help me")
    assert is_greeting("How can you help me?")
    assert is_greeting("  what can you do?!  ")


def test_clinical_question_is_not_mistaken_for_a_greeting() -> None:
    assert not is_greeting("Can you help me manage suspected adrenal crisis?")


def test_capability_response_describes_eva_scope() -> None:
    assert "adrenal insufficiency" in GREETING_RESPONSE_EN
    assert "NICE guideline NG243" in GREETING_RESPONSE_EN
