"""FastAPI application entry point.

Development runs two processes (this on :8000, Next.js on :3000 proxying /api/*).
Production serves the frontend's static export from here, collapsing to one
deployable (plan.md Structure Decision).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import generate, search
from backend.app.config import REPO_ROOT, get_settings

app = FastAPI(
    title="Clinical Decision Support Lite",
    description=(
        "Retrieval over official clinical guidelines. Day 1 scope: ingestion and "
        "retrieval only — generation is intentionally unimplemented "
        "(Constitution Principle V)."
    ),
    version="1.0.0",
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

# Production only: serve the Next.js static export if it has been built.
_static_dir = REPO_ROOT / "frontend" / "out"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="frontend")
