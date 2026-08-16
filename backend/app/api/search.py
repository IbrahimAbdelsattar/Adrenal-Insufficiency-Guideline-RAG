"""Retrieval endpoints (contracts/search-api.yaml)."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import get_settings
from backend.app.errors import PipelineError
from backend.app.models import DISCLAIMER, IndexManifest, SearchResponse
from backend.app.retrieval.dense import DenseRetriever
from backend.app.retrieval.store import VectorStore

router = APIRouter(prefix="/api", tags=["retrieval"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=0, ge=0, le=50)


@router.get("/health")
def get_health() -> dict:
    """Liveness plus index readiness."""
    try:
        ready = VectorStore().is_ready()
    except Exception as exc:  # an unavailable store is degraded, not fatal
        return {"status": "degraded", "index_ready": False, "message": str(exc)}

    return {
        "status": "ok",
        "index_ready": ready,
        "message": (
            "Index ready."
            if ready
            else "No index built yet - run: python -m backend.app.cli ingest"
        ),
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

    return SearchResponse(
        query=request.query,
        results=results,
        result_count=len(results),
        evidence_found=any(not r.below_floor for r in results),
        embedding_model=settings.embedding_model,
        latency_ms=int((time.perf_counter() - started) * 1000),
        disclaimer=DISCLAIMER,
    )
