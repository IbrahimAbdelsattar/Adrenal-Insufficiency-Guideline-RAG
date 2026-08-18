"""Unit tests for hybrid search configuration settings."""

from backend.app.config import Settings


def test_hybrid_config_defaults():
    """New hybrid search settings have correct defaults."""
    # Build a fresh Settings instance (bypass lru_cache)
    settings = Settings()
    assert hasattr(settings, "retriever_type")
    assert settings.retriever_type in ("dense", "hybrid", "hybrid_rerank")
    assert hasattr(settings, "reranker_model")
    assert isinstance(settings.reranker_model, str)
    assert len(settings.reranker_model) > 0
    assert hasattr(settings, "hybrid_candidate_k")
    assert settings.hybrid_candidate_k >= 10


def test_retriever_type_default_is_hybrid():
    """Default retriever is plain hybrid (reranker off by default: the Day 2
    eval showed it lowers hit rate while adding latency)."""
    settings = Settings()
    assert settings.retriever_type == "hybrid"


def test_reranker_model_default():
    """Default reranker model is ms-marco-MiniLM."""
    settings = Settings()
    assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_hybrid_candidate_k_default():
    """Default hybrid candidate pool is 20."""
    settings = Settings()
    assert settings.hybrid_candidate_k == 20
