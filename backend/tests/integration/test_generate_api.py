"""Integration test for the generation API."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


@pytest.fixture
def mock_llm(monkeypatch):
    """Mocks the LLMClient.generate_completion method."""
    from backend.app.generation.client import LLMClient

    async def mock_generate(self, system_prompt: str, user_prompt: str) -> str:
        return "This is a mock answer based on [Source 1]."

    monkeypatch.setattr(LLMClient, "generate_completion", mock_generate)


def test_generate_api_abstains_when_no_evidence(monkeypatch):
    """When no evidence is found or out of scope, the endpoint should return an abstention message without calling LLM."""
    import backend.app.api.generate as generate_module
    from backend.app.generation.client import LLMClient

    called = False

    async def mock_generate(self, system_prompt: str, user_prompt: str) -> str:
        nonlocal called
        called = True
        return "I should not be called."

    class MockRetriever:
        def search(self, query: str, top_k: int) -> list:
            return []

    monkeypatch.setattr(LLMClient, "generate_completion", mock_generate)
    monkeypatch.setattr(generate_module, "get_retriever", lambda s: MockRetriever())

    response = client.post(
        "/api/generate",
        json={"query": "asdfasdfasdfasdf", "top_k": 3},
    )

    if response.status_code == 503:
        pytest.skip("Index not built, cannot test generation API")

    assert response.status_code == 200
    data = response.json()

    assert data["evidence_found"] is False
    assert (
        "outside the current scope" in data["answer"]
        or "could not find enough relevant information" in data["answer"]
        or "no strong supporting evidence" in data["answer"].lower()
    )
    assert len(data["citations"]) == 0
    assert not called


def test_generate_api_with_evidence(mock_llm):
    """When evidence is found, the endpoint should call the LLM and extract citations."""
    response = client.post(
        "/api/generate",
        json={"query": "Hydrocortisone adrenal crisis", "top_k": 3},
    )

    if response.status_code == 503:
        pytest.skip("Index not built, cannot test generation API")

    assert response.status_code == 200
    data = response.json()

    assert data["evidence_found"] is True
    assert "mock answer based on [Source 1]" in data["answer"]
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["source_id"] == "1"
    assert "document_name" in data["citations"][0]
