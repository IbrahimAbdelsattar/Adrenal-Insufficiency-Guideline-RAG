"""Retrieval endpoints (contracts/search-api.yaml).

Phase 2 provides /api/health. Search, index and sources arrive in later phases.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.retrieval.store import VectorStore

router = APIRouter(prefix="/api", tags=["retrieval"])


@router.get("/health")
def get_health() -> dict:
    """Liveness plus index readiness."""
    try:
        ready = VectorStore().is_ready()
    except Exception as exc:  # store unavailable is degraded, not fatal
        return {"status": "degraded", "index_ready": False, "message": str(exc)}

    return {
        "status": "ok",
        "index_ready": ready,
        "message": (
            "Index ready." if ready else "No index built yet — run: python -m backend.app.cli ingest"
        ),
    }
