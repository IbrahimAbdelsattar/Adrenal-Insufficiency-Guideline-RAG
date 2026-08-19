"""Unit tests for multi-tier RAG caching architecture (TTLLRUCache, normalize_query, and response cache)."""

import time
from pathlib import Path
from backend.app.retrieval.cache import TTLLRUCache, normalize_query
from backend.app.api.generate import _cache_key
from backend.app.models import Chunk, RetrievalResult


def test_normalize_query_strips_whitespace_and_punctuation():
    assert normalize_query("  What is adrenal crisis??? ") == "what is adrenal crisis"
    assert normalize_query("What is the DOSE for 1.7.1?") == "what is the dose for 1.7.1"
    assert normalize_query("   ") == ""


def test_ttl_lru_cache_basic_put_and_get():
    cache = TTLLRUCache[str, str](maxsize=10, ttl_seconds=60.0, name="test_cache")
    assert cache.get("k1") is None

    cache.put("k1", "v1")
    assert cache.get("k1") == "v1"
    assert len(cache) == 1

    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1


def test_ttl_lru_cache_lru_eviction():
    cache = TTLLRUCache[str, int](maxsize=3, ttl_seconds=60.0)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    # Access 'a' so 'b' becomes the oldest
    assert cache.get("a") == 1

    # Adding 'd' should evict 'b'
    cache.put("d", 4)
    assert len(cache) == 3
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_ttl_lru_cache_ttl_expiration():
    # Cache with very short TTL
    cache = TTLLRUCache[str, str](maxsize=5, ttl_seconds=0.05)
    cache.put("key", "value")
    assert cache.get("key") == "value"

    # Wait for TTL to elapse
    time.sleep(0.08)
    assert cache.get("key") is None
    assert len(cache) == 0


def test_ttl_lru_cache_manifest_invalidation(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text('{"built_at": "2026-01-01T00:00:00Z"}')

    cache = TTLLRUCache[str, str](maxsize=5, ttl_seconds=3600.0, manifest_path=manifest_file)
    cache.put("q1", "ans1")
    assert cache.get("q1") == "ans1"

    # Simulate index re-ingest by modifying manifest file mtime
    time.sleep(0.05)
    manifest_file.write_text('{"built_at": "2026-01-02T00:00:00Z"}')

    # Cache should detect mtime change and flush
    assert cache.get("q1") is None
    assert len(cache) == 0


def test_generate_cache_key_with_history():
    chunk = Chunk(
        chunk_id="doc1_p1_c1",
        text="Sample text",
        token_count=10,
        doc_id="doc1",
        document_name="NG243",
        page_number=1,
        section_title="Emergency",
        section_number="1.7",
        source_url="http://example.com",
        document_type="guideline",
        publication_year=2024,
        requires_caution=False,
        is_oversized=False,
    )
    result = RetrievalResult(
        chunk=chunk,
        score=0.9,
        rank=1,
        below_floor=False,
        dense_score=0.85,
    )

    key1 = _cache_key("What is the dose?", 3, [result])
    key2 = _cache_key("  WHAT is the DOSE?  ", 3, [result])
    assert key1 == key2

    key_with_history = _cache_key(
        "What is the dose?",
        3,
        [result],
        history=[{"role": "user", "content": "Adrenal crisis?"}],
    )
    assert key_with_history != key1
    assert "hist:user:adrenal crisis" in key_with_history


def test_retrieval_cache_integration():

    from backend.app.api.search import _RETRIEVAL_CACHE

    _RETRIEVAL_CACHE.clear()
    key = (normalize_query("adrenal crisis hydrocortisone"), 3, "hybrid")
    assert _RETRIEVAL_CACHE.get(key) is None

    chunk = Chunk.from_stored(
        "ng243_p14_c1",
        "Hydrocortisone 100mg IV or IM immediately.",
        {
            "doc_id": "nice_ng243",
            "document_name": "NICE NG243",
            "source_url": "https://www.nice.org.uk/guidance/ng243",
            "document_type": "guideline",
            "publication_year": 2024,
            "requires_caution": False,
            "page_number": 14,
            "section_title": "Emergency management",
            "section_number": "1.7",
            "subsection_title": "",
            "recommendation_ids": "1.7.1",
            "token_count": 12,
            "is_oversized": False,
        },
    )
    result = RetrievalResult(
        chunk=chunk,
        score=1.0,
        rank=1,
        below_floor=False,
        dense_score=0.88,
        retriever_mode="hybrid",
    )

    _RETRIEVAL_CACHE.put(key, ([result], "in_scope", "Evidence found", [result]))

    # Cache hit
    cached = _RETRIEVAL_CACHE.get(key)
    assert cached is not None
    assert cached[1] == "in_scope"
    assert len(cached[0]) == 1
    assert cached[0][0].chunk.chunk_id == "ng243_p14_c1"
    assert _RETRIEVAL_CACHE.stats()["hits"] == 1


def test_generation_response_cache_integration():
    from backend.app.api.generate import _RESPONSE_CACHE, _cache_get, _cache_put

    _RESPONSE_CACHE.clear()
    key = "3|adrenal crisis hydrocortisone|ng243_p14_c1"
    assert _cache_get(key) is None

    entry = {
        "answer": "Administer 100 mg hydrocortisone immediately via IV or IM injection [Source 1].",
        "citations": [{"source_number": 1, "document_name": "NICE NG243", "section_number": "1.7"}],
        "model": "eva-ai",
    }
    _cache_put(key, entry)

    cached = _cache_get(key)
    assert cached is not None
    assert "100 mg hydrocortisone" in cached["answer"]
    assert cached["model"] == "eva-ai"
    assert len(cached["citations"]) == 1
