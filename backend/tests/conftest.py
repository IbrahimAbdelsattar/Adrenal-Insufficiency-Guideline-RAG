"""Shared pytest configuration and fixtures for Eva AI test suite."""

import pytest


@pytest.fixture(autouse=True)
def _clear_all_rag_caches():
    """Ensure in-memory response and retrieval caches are pristine before each test."""
    try:
        from backend.app.generation.service import cache_clear as clear_generation_cache

        clear_generation_cache()
    except Exception:
        pass

    try:
        from backend.app.api.search import _RETRIEVAL_CACHE

        _RETRIEVAL_CACHE.clear()
    except Exception:
        pass

    yield

    try:
        from backend.app.generation.service import cache_clear as clear_generation_cache

        clear_generation_cache()
    except Exception:
        pass

    try:
        from backend.app.api.search import _RETRIEVAL_CACHE

        _RETRIEVAL_CACHE.clear()
    except Exception:
        pass
