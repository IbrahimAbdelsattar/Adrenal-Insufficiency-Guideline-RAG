"""FastAPI application entry point.

Development runs two processes (this on :8000, Next.js on :3000 proxying /api/*).
Production serves the frontend's static export from here, collapsing to one
deployable (plan.md Structure Decision).
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import generate, search
from backend.app.config import REPO_ROOT, get_settings
from backend.app.monitoring import (
    REGISTRY,
    configure_logging,
    get_request_id,
    init_langsmith,
    init_sentry,
    reset_request_id,
    set_request_id,
)

# Logging is configured before anything else can emit: handlers installed
# after the first record would silently lose those lines.
_settings = get_settings()
configure_logging(_settings)

logger = logging.getLogger(__name__)

# Initialize Sentry error tracking & monitoring
init_sentry(_settings)

# Initialize LangSmith RAG tracing
init_langsmith(_settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm models and indices on startup to eliminate cold-start latency."""
    settings = get_settings()

    logger.info(
        "Startup: retriever=%s generation_model=%s embedding_model=%s top_k=%d",
        settings.retriever_type,
        settings.generation_model,
        settings.embedding_model,
        settings.top_k,
        extra={
            "event": "startup.config",
            "retriever_type": settings.retriever_type,
            "generation_model": settings.generation_model,
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k,
            "relevance_floor": settings.relevance_floor,
            "scope_threshold": settings.scope_threshold,
            "graph_expansion": settings.graph_expansion,
            "response_cache_size": settings.response_cache_size,
            "log_level": settings.log_level,
        },
    )
    warmup_started = time.perf_counter()

    # Pre-warm CrossEncoder reranker model
    if settings.retriever_type in ("hybrid_rerank", "rerank"):
        try:
            from backend.app.retrieval.reranker import CrossEncoderReranker

            started = time.perf_counter()
            reranker = CrossEncoderReranker(settings=settings)
            reranker._get_model()
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Lifespan: CrossEncoder pre-warmed in %.0f ms.",
                elapsed_ms,
                extra={
                    "event": "startup.prewarm",
                    "component": "cross_encoder",
                    "model": settings.reranker_model,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
        except Exception as exc:
            logger.warning("Lifespan: CrossEncoder pre-warm warning: %s", exc)

    # Pre-warm the shared retriever: opens Chroma and builds the BM25 index
    # once at startup so no request pays that cost.
    try:
        from backend.app.retrieval.factory import get_shared_retriever, get_shared_store

        started = time.perf_counter()
        retriever = get_shared_retriever(settings)
        bm25 = getattr(retriever, "_bm25", None)
        if bm25 is not None and not bm25._indexed:
            bm25._build_index()
        chunk_count = get_shared_store(settings).count()
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Lifespan: shared retriever pre-warmed in %.0f ms (indexed_chunks=%d).",
            elapsed_ms,
            chunk_count,
            extra={
                "event": "startup.prewarm",
                "component": "retriever",
                "retriever_type": settings.retriever_type,
                "indexed_chunks": chunk_count,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
    except Exception as exc:
        logger.warning("Lifespan: shared retriever pre-warm warning: %s", exc)

    total_warmup_ms = (time.perf_counter() - warmup_started) * 1000
    logger.info(
        "Startup complete in %.0f ms.",
        total_warmup_ms,
        extra={"event": "startup.complete", "duration_ms": round(total_warmup_ms, 2)},
    )

    yield

    logger.info(
        "Shutdown: final latency snapshot",
        extra={"event": "shutdown", "metrics": REGISTRY.snapshot()},
    )


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


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Assign a correlation id and log one line per HTTP request.

    Every RAG and LLM line emitted while handling the request carries the same
    `request_id`, so one grep reconstructs the entire call end to end. An
    inbound X-Request-ID is honoured so a trace can span frontend and backend.
    """
    token = set_request_id(request.headers.get("x-request-id"))
    request_id = get_request_id()
    settings = get_settings()
    started = time.perf_counter()
    status_code = 500
    response: Response | None = None

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        logger.exception(
            "request.failed %s %s",
            request.method,
            request.url.path,
            extra={
                "event": "request.failed",
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        path = request.url.path
        REGISTRY.observe(f"http.{request.method}.{path}", duration_ms)
        REGISTRY.increment(f"http.status.{status_code // 100}xx")

        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-ms"] = f"{duration_ms:.1f}"

        slow = duration_ms >= settings.slow_request_ms
        logger.log(
            logging.WARNING if (slow or status_code >= 500) else logging.INFO,
            "%s %s -> %d in %.1f ms%s",
            request.method,
            path,
            status_code,
            duration_ms,
            " [SLOW]" if slow else "",
            extra={
                "event": "request",
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "slow": slow,
            },
        )
        reset_request_id(token)


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
