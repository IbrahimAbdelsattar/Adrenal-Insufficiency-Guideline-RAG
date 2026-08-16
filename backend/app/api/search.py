"""Retrieval endpoints (contracts/search-api.yaml)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.errors import PipelineError
from backend.app.models import DISCLAIMER, IndexManifest, SearchResponse
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["retrieval"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=0, ge=0, le=50)


@router.get("/health")
def get_health() -> dict:
    """Liveness, index readiness, and configuration state.

    Reports whether the gateway key is present and whether the configured model
    matches the one the index was built with. Both are silent misconfigurations
    that otherwise only surface as a failed search — never returns the key.
    """
    settings = get_settings()
    key_configured = bool(settings.openrouter_api_key)

    try:
        store = VectorStore(settings)
        ready = store.is_ready()
        manifest = store.read_manifest()
    except Exception as exc:  # an unavailable store is degraded, not fatal
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
        "message": "; ".join(problems) if problems else "Index ready.",
    }


@router.get("/index", response_model=IndexManifest)
def get_index_status() -> IndexManifest:
    """The manifest describing how the current index was built (FR-030)."""
    manifest = VectorStore().read_manifest()
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail="No index has been built. Run: python -m backend.app.cli ingest",
        )
    return manifest


@router.get("/sources")
def list_sources() -> dict:
    """Provenance registry, for review (FR-001, User Story 4)."""
    from backend.app.ingestion.registry import load_registry

    try:
        documents = load_registry()
    except PipelineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "sources": [
            {
                **doc.model_dump(mode="json", exclude={"filename"}),
                "requires_caution": doc.requires_caution(),
            }
            for doc in documents
        ]
    }


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    """Dense top-K retrieval with full citation metadata (FR-021 to FR-025)."""
    settings = get_settings()
    store = VectorStore(settings)

    if not store.is_ready():
        raise HTTPException(
            status_code=503,
            detail="No evidence is available: the index is empty. "
            "Run: python -m backend.app.cli ingest",
        )

    # An index built with a different model lives in a different vector space.
    manifest = store.read_manifest()
    if manifest and manifest.embedding_model != settings.embedding_model:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Index was built with '{manifest.embedding_model}' but the app is "
                f"configured for '{settings.embedding_model}'. Re-run ingest."
            ),
        )

    started = time.perf_counter()
    try:
        results = DenseRetriever(store=store, settings=settings).search(
            request.query, request.top_k or settings.top_k
        )
    except PipelineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    above_floor = sum(1 for r in results if not r.below_floor)
    logger.info(
        "search results=%d above_floor=%d top_score=%.3f latency_ms=%d",
        len(results),
        above_floor,
        results[0].score if results else 0.0,
        latency_ms,
    )

    return SearchResponse(
        query=request.query,
        results=results,
        result_count=len(results),
        evidence_found=above_floor > 0,
        embedding_model=settings.embedding_model,
        latency_ms=latency_ms,
        disclaimer=DISCLAIMER,
    )
