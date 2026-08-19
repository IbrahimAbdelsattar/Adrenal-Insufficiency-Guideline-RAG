"""Retrieval endpoints (contracts/search-api.yaml)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.errors import PipelineError
from backend.app.models import DISCLAIMER, IndexManifest, RetrievalResult, SearchResponse
from backend.app.monitoring import REGISTRY, RagTrace
from backend.app.retrieval.cache import TTLLRUCache, normalize_query
from backend.app.retrieval.factory import get_shared_retriever, get_shared_store
from backend.app.retrieval.scope import classify_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["retrieval"])

# Bounded TTL + LRU retrieval cache for instant repeat searches
_RETRIEVAL_CACHE: TTLLRUCache[tuple[str, int, str], tuple[list[RetrievalResult], str, str, list[RetrievalResult]]] = (
    TTLLRUCache(
        maxsize=get_settings().retrieval_cache_size,
        ttl_seconds=get_settings().cache_ttl_seconds,
        manifest_path=get_settings().index_dir / "manifest.json",
        name="retrieval_search_cache",
    )
)



class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=0, ge=0, le=50)


@router.get("/health")
def get_health() -> dict:
    """Liveness, index readiness, and configuration state.

    Reports whether the gateway key is present and whether the configured model
    matches the one the index was built with.
    """
    settings = get_settings()
    key_configured = bool(settings.openrouter_api_key)

    try:
        store = get_shared_store(settings)
        ready = store.is_ready()
        manifest = store.read_manifest()
    except Exception as exc:
        return {
            "status": "degraded",
            "index_ready": False,
            "api_key_configured": key_configured,
            "message": str(exc),
        }

    index_model = manifest.embedding_model if manifest else ""
    model_matches = (not index_model) or index_model == settings.embedding_model

    problems = []

    if not ready:
        problems.append("No index built - run: python -m backend.app.cli ingest")

    if not key_configured:
        problems.append("OMNIROUTE_API_KEY is not set - search cannot embed queries")

    if not model_matches:
        problems.append(
            f"Index was built with '{index_model}' but EMBEDDING_MODEL is "
            f"'{settings.embedding_model}' - re-ingest or revert the setting"
        )

    return {
        "status": "ok" if not problems else "degraded",
        "index_ready": ready,
        "api_key_configured": key_configured,
        "embedding_model": settings.embedding_model,
        "index_embedding_model": index_model,
        "model_matches_index": model_matches,
        "retriever_type": settings.retriever_type,
        "message": "; ".join(problems) if problems else "Index ready.",
    }


@router.get("/metrics", tags=["monitoring"])
def get_metrics() -> dict:
    """Rolling latency and counter snapshot for this worker process.

    Per-stage `count / avg / p50 / p95 / max` over the last N observations
    plus lifetime counters (cache hits, scope outcomes, LLM calls, retries,
    errors). In-memory and per-process: a live read-out for tuning the RAG
    pipeline, not a substitute for a metrics backend.
    """
    settings = get_settings()
    snapshot = REGISTRY.snapshot()
    return {
        "status": "ok",
        "config": {
            "retriever_type": settings.retriever_type,
            "generation_model": settings.generation_model,
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k,
            "relevance_floor": settings.relevance_floor,
            "scope_threshold": settings.scope_threshold,
            "graph_expansion": settings.graph_expansion,
        },
        **snapshot,
    }


@router.get("/health/sentry-test")
def sentry_test_diagnostic(trigger_error: bool = False) -> dict:
    """Diagnostic endpoint to test and verify Sentry error capture."""
    import sentry_sdk

    from backend.app.monitoring.sentry import is_sentry_enabled

    sentry_active = is_sentry_enabled()

    if trigger_error:
        class SentryTestException(Exception):
            pass

        try:
            raise SentryTestException("Manual test exception triggered for Sentry verification")
        except SentryTestException as exc:
            sentry_sdk.capture_exception(exc)
            return {
                "status": "test_exception_captured",
                "error_type": "SentryTestException",
                "detail": str(exc),
                "sentry_enabled": sentry_active,
            }

    sentry_sdk.capture_message("Sentry health test diagnostic executed.", level="info")
    return {
        "status": "ok",
        "sentry_enabled": sentry_active,
        "message": "Sentry test diagnostic triggered successfully.",
    }



@router.get("/index", response_model=IndexManifest)
def get_index_status() -> IndexManifest:
    """The manifest describing how the current index was built (FR-030)."""

    manifest = get_shared_store().read_manifest()

    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=("No index has been built. Run: python -m backend.app.cli ingest"),
        )

    return manifest


@router.get("/sources")
def list_sources() -> dict:
    """Provenance registry, for review (FR-001, User Story 4)."""

    from backend.app.ingestion.registry import load_registry

    try:
        documents = load_registry()
    except PipelineError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return {
        "sources": [
            {
                **doc.model_dump(
                    mode="json",
                    exclude={"filename"},
                ),
                "requires_caution": doc.requires_caution(),
            }
            for doc in documents
        ]
    }


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    """Top-K retrieval with scope detection and citation metadata."""

    settings = get_settings()
    store = get_shared_store(settings)
    top_k = request.top_k or settings.top_k
    trace = RagTrace("search", query=request.query, top_k=top_k, settings=settings)

    if not store.is_ready():
        logger.error(
            "Search rejected: index is empty.",
            extra={"event": "search.no_index"},
        )
        trace.set(error="index_empty")
        trace.emit(status="error", level=logging.ERROR)
        raise HTTPException(
            status_code=503,
            detail=(
                "No evidence is available: the index is empty. "
                "Run: python -m backend.app.cli ingest"
            ),
        )

    manifest = store.read_manifest()
    if manifest and manifest.embedding_model != settings.embedding_model:
        logger.error(
            "Search rejected: index/embedding model mismatch (%s != %s).",
            manifest.embedding_model,
            settings.embedding_model,
            extra={
                "event": "search.model_mismatch",
                "index_embedding_model": manifest.embedding_model,
                "configured_embedding_model": settings.embedding_model,
            },
        )
        trace.set(error="model_mismatch")
        trace.emit(status="error", level=logging.ERROR)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Index was built with '{manifest.embedding_model}' but the app "
                f"is configured for '{settings.embedding_model}'. Re-run ingest."
            ),
        )

    started = time.perf_counter()
    cache_key = (normalize_query(request.query), top_k, settings.retriever_type)
    cached_entry = _RETRIEVAL_CACHE.get(cache_key)

    if cached_entry is not None:
        results, scope_status, scope_message, filtered_results = cached_entry
        latency_ms = int((time.perf_counter() - started) * 1000)
        trace.record_retrieval(results)
        REGISTRY.increment(f"search.scope.{scope_status}")
        REGISTRY.increment("search.cache.hit")
        trace.set(
            scope_status=scope_status,
            returned=len(filtered_results),
            evidence_found=scope_status == "in_scope",
            cache_hit=True,
        )
        trace.emit(status="ok_cached")
        return SearchResponse(
            query=request.query,
            results=filtered_results,
            result_count=len(filtered_results),
            evidence_found=scope_status == "in_scope",
            scope_status=scope_status,
            scope_message=scope_message,
            embedding_model=settings.embedding_model,
            latency_ms=latency_ms,
            disclaimer=DISCLAIMER,
        )

    REGISTRY.increment("search.cache.miss")
    try:
        with trace.stage("retrieval", top_k=top_k, retriever_type=settings.retriever_type) as span:
            retriever = get_shared_retriever(settings)
            results = retriever.search(request.query, top_k)
            span["results"] = len(results)
    except PipelineError as exc:
        trace.set(error=str(exc), error_type="PipelineError")
        trace.emit(status="error", level=logging.ERROR)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    trace.record_retrieval(results)

    with trace.stage("scope", scope_threshold=settings.scope_threshold) as span:
        scope_status, scope_message, filtered_results = classify_scope(
            results, settings.scope_threshold, query=request.query
        )

        span["scope_status"] = scope_status
        span["kept"] = len(filtered_results)

    # Save to retrieval cache
    _RETRIEVAL_CACHE.put(cache_key, (results, scope_status, scope_message, filtered_results))

    REGISTRY.increment(f"search.scope.{scope_status}")
    trace.set(
        scope_status=scope_status,
        returned=len(filtered_results),
        evidence_found=scope_status == "in_scope",
        cache_hit=False,
    )
    trace.emit(status="ok")

    return SearchResponse(
        query=request.query,
        results=filtered_results,
        result_count=len(filtered_results),
        evidence_found=scope_status == "in_scope",
        scope_status=scope_status,
        scope_message=scope_message,
        embedding_model=settings.embedding_model,
        latency_ms=latency_ms,
        disclaimer=DISCLAIMER,
    )

