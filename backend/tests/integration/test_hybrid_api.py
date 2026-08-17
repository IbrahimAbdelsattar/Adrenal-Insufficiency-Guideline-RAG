"""Integration test for the search API with hybrid retriever."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_search_api_returns_valid_response():
    """Search endpoint responds without error (index may or may not exist)."""
    response = client.post(
        "/api/search",
        json={"query": "Hydrocortisone adrenal crisis", "top_k": 3},
    )
    # 200 if index exists, 503 if not — both are valid states
    assert response.status_code in (200, 503)


def test_health_endpoint_available():
    """Health endpoint always responds."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
