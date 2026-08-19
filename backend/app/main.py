"""FastAPI application entry point.

Development runs two processes (this on :8000, Next.js on :3000 proxying /api/*).
Production serves the frontend's static export from here, collapsing to one
deployable (plan.md Structure Decision).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import generate, search
from backend.app.config import REPO_ROOT, get_settings
from backend.app.monitoring import init_sentry

logger = logging.getLogger(__name__)

# Initialize Sentry error tracking & monitoring
_settings = get_settings()
init_sentry(_settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm models and indices on startup to eliminate cold-start latency."""
    settings = get_settings()

    # Pre-warm CrossEncoder reranker model
    if settings.retriever_type in ("hybrid_rerank", "rerank"):
        try:
            from backend.app.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker(settings=settings)
            reranker._get_model()
            logger.info("Lifespan: CrossEncoder pre-warmed successfully.")
        except Exception as exc:
            logger.warning("Lifespan: CrossEncoder pre-warm warning: %s", exc)

    # Pre-warm the shared retriever: opens Chroma and builds the BM25 index
    # once at startup so no request pays that cost.
    try:
        from backend.app.retrieval.factory import get_shared_retriever

        retriever = get_shared_retriever(settings)
        bm25 = getattr(retriever, "_bm25", None)
        if bm25 is not None and not bm25._indexed:
            bm25._build_index()
        logger.info("Lifespan: shared retriever pre-warmed successfully.")
    except Exception as exc:
        logger.warning("Lifespan: shared retriever pre-warm warning: %s", exc)

    yield


app = FastAPI(
    title="Eva AI Clinical Decision Support",
    description=(
        "Retrieval over official clinical guidelines. Day 1 scope: ingestion and "
        "retrieval only — generation is intentionally unimplemented "
        "(Constitution Principle V)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()

# allow_origin_regex covers the deployed frontend/backend subdomain split, so
# cross-origin calls keep working even if ALLOWED_ORIGINS is not set on the host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_origin_regex=_settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)

app.include_router(search.router)
app.include_router(generate.router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
def favicon_png():
    return Response(status_code=204)


@app.get("/sentry-debug", tags=["monitoring"])
@app.get("/sentry-debug/", include_in_schema=False)
async def trigger_error():
    """Trigger a division by zero error to verify Sentry integration."""
    divisor = 0
    return 1 / divisor




# Production only: serve the Next.js static export if it has been built.
_static_dir = REPO_ROOT / "frontend" / "out"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="frontend")
else:

    @app.get("/", include_in_schema=False)
    def api_root():
        return {
            "service": "Eva AI Clinical Decision Support API",
            "status": "online",
            "docs": "/docs",
            "health": "/api/health",
        }
