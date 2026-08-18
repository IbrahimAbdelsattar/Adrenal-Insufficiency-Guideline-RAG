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
    monkeypatch.setattr(generate_module, "get_shared_retriever", lambda s: MockRetriever())

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


def test_generate_response_cache_avoids_second_llm_call(monkeypatch):
    """An identical repeat query must be served from cache without another LLM call."""
    from backend.app.generation.client import LLMClient

    calls = {"n": 0}

    async def counting_generate(self, system_prompt: str, user_prompt: str) -> str:
        calls["n"] += 1
        return "Cached mock answer [Source 1]."

    monkeypatch.setattr(LLMClient, "generate_completion", counting_generate)

    payload = {"query": "What is sick-day dosing of hydrocortisone?", "top_k": 3}

    first = client.post("/api/generate", json=payload)
    if first.status_code == 503:
        pytest.skip("Index not built, cannot test generation API")
    assert first.status_code == 200
    assert first.json()["cache_hit"] is False
    assert calls["n"] == 1

    second = client.post("/api/generate", json=payload)
    assert second.status_code == 200
    data = second.json()

    assert data["cache_hit"] is True
    assert data["answer"] == "Cached mock answer [Source 1]."
    assert calls["n"] == 1, "cached response must not call the LLM again"


def test_generate_stream_emits_meta_token_done(monkeypatch):
    """The SSE endpoint streams meta -> token(s) -> done with citations."""
    import json

    from backend.app.generation.client import LLMClient

    async def mock_stream(self, system_prompt: str, user_prompt: str):
        yield "Adrenal crisis requires "
        yield "100 mg hydrocortisone [Source 1]."

    monkeypatch.setattr(LLMClient, "stream_completion", mock_stream)

    response = client.post(
        "/api/generate/stream",
        json={"query": "Streaming adrenal crisis management", "top_k": 3},
    )

    if response.status_code == 503:
        pytest.skip("Index not built, cannot test streaming API")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events: dict[str, list[dict]] = {}
    for block in response.text.split("\n\n"):
        lines = block.splitlines()
        event = next(
            (line.split(":", 1)[1].strip() for line in lines if line.startswith("event:")), None
        )
        data_line = next(
            (line.split(":", 1)[1].strip() for line in lines if line.startswith("data:")), None
        )
        if event and data_line:
            events.setdefault(event, []).append(json.loads(data_line))

    assert events["meta"][0]["evidence_found"] is True
    assert events["meta"][0]["cache_hit"] is False

    full_answer = "".join(t["text"] for t in events["token"])
    assert "100 mg hydrocortisone" in full_answer

    done = events["done"][0]
    assert done["citations"][0]["source_id"] == "1"
    assert done["disclaimer"]


def test_generate_stream_cache_hit(monkeypatch):
    """A streamed repeat query is served from cache as a single token event."""
    import json

    from backend.app.generation.client import LLMClient

    calls = {"n": 0}

    async def counting_stream(self, system_prompt: str, user_prompt: str):
        calls["n"] += 1
        yield "Streamed answer [Source 1]."

    monkeypatch.setattr(LLMClient, "stream_completion", counting_stream)

    payload = {"query": "Stream repeat query hydrocortisone", "top_k": 3}

    first = client.post("/api/generate/stream", json=payload)
    if first.status_code == 503:
        pytest.skip("Index not built, cannot test streaming API")

    second = client.post("/api/generate/stream", json=payload)
    meta_blocks = [
        json.loads(line.split(":", 1)[1].strip())
        for line in second.text.splitlines()
        if line.startswith("data:") and "cache_hit" in line
    ]

    assert meta_blocks and meta_blocks[0]["cache_hit"] is True
    assert calls["n"] == 1, "cached stream must not call the LLM again"
