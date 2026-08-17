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


# ---------------------------------------------------------------------------
# Scope / relevance thresholds
# ---------------------------------------------------------------------------

# Current evidence threshold used by the existing retrieval system.
#
# Scores below this value are considered weak evidence.
# This value is already represented by the retriever's `below_floor` field.
#
# We use a HIGHER threshold for scope detection because:
#
#   0.30  -> weak evidence threshold
#   0.65  -> scope threshold
#
# This gives us three states:
#
#   score >= 0.65
#       Strongly related to the indexed topic.
#
#   0.30 <= score < 0.65
#       Possibly related, but evidence is not strong enough.
#
#   score < 0.30
#       Very weak similarity.
#
# NOTE:
# This threshold should eventually be tuned using the project's
# evaluation/golden questions.
SCOPE_THRESHOLD = 0.65


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
    except Exception as exc:
        return {
            "status": "degraded",
            "index_ready": False,
            "api_key_configured": key_configured,
            "message": str(exc),
        }

    index_model = manifest.embedding_model if manifest else ""
    model_matches = (
        (not index_model)
        or index_model == settings.embedding_model
    )

    problems = []

    if not ready:
        problems.append(
            "No index built - run: python -m backend.app.cli ingest"
        )

    if not key_configured:
        problems.append(
            "OMNIROUTE_API_KEY is not set - search cannot embed queries"
        )

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
        "message": "; ".join(problems)
        if problems
        else "Index ready.",
    }


@router.get("/index", response_model=IndexManifest)
def get_index_status() -> IndexManifest:
    """The manifest describing how the current index was built (FR-030)."""

    manifest = VectorStore().read_manifest()

    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No index has been built. "
                "Run: python -m backend.app.cli ingest"
            ),
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
    """Dense top-K retrieval with scope detection and citation metadata."""

    settings = get_settings()
    store = VectorStore(settings)

    # -----------------------------------------------------------------------
    # 1. Check whether the vector index exists
    # -----------------------------------------------------------------------

    if not store.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "No evidence is available: the index is empty. "
                "Run: python -m backend.app.cli ingest"
            ),
        )

    # -----------------------------------------------------------------------
    # 2. Make sure the embedding model matches the index
    # -----------------------------------------------------------------------

    manifest = store.read_manifest()

    if (
        manifest
        and manifest.embedding_model != settings.embedding_model
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Index was built with '{manifest.embedding_model}' but the app "
                f"is configured for '{settings.embedding_model}'. Re-run ingest."
            ),
        )

    # -----------------------------------------------------------------------
    # 3. Perform vector retrieval
    # -----------------------------------------------------------------------

    started = time.perf_counter()

    try:
        results = DenseRetriever(
            store=store,
            settings=settings,
        ).search(
            request.query,
            request.top_k or settings.top_k,
        )

    except PipelineError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    latency_ms = int(
        (time.perf_counter() - started) * 1000
    )

    # -----------------------------------------------------------------------
    # 4. Analyze similarity scores
    # -----------------------------------------------------------------------

    above_floor = sum(
        1
        for result in results
        if not result.below_floor
    )

    top_score = (
        results[0].score
        if results
        else 0.0
    )

    logger.info(
        "search results=%d above_floor=%d top_score=%.3f latency_ms=%d",
        len(results),
        above_floor,
        top_score,
        latency_ms,
    )

    # -----------------------------------------------------------------------
    # 5. Determine scope status
    # -----------------------------------------------------------------------
    #
    # IMPORTANT:
    #
    # We don't simply use `below_floor` here.
    #
    # The existing floor (0.30) answers:
    #
    #     "Is this result strong enough to be considered evidence?"
    #
    # The scope threshold (0.65) answers:
    #
    #     "Does this question appear sufficiently related to the
    #      topic covered by our current knowledge base?"
    #
    # This gives us a clean distinction between:
    #
    # OUT OF SCOPE
    #     score < 0.65
    #
    # NO EVIDENCE
    #     score >= 0.65 but no result is above the evidence floor
    #
    # EVIDENCE FOUND
    #     score >= 0.65 and at least one result is above the floor.
    # -----------------------------------------------------------------------

    if not results or top_score < SCOPE_THRESHOLD:
        scope_status = "out_of_scope"

        scope_message = (
            "This question is outside the current scope of Eva AI. "
            "Eva AI currently covers adrenal insufficiency, including "
            "its identification and management, based on the registered "
            "NICE NG243 guideline."
        )

        # VERY IMPORTANT:
        #
        # Do not return unrelated chunks to the frontend.
        #
        # Otherwise the UI would display exactly the problem you currently
        # have: asking "what meaning of AI" and receiving glucocorticoid
        # withdrawal evidence.
        filtered_results = []

    elif above_floor > 0:
        scope_status = "in_scope"

        scope_message = (
            "Relevant clinical evidence was found in the registered "
            "guideline."
        )

        filtered_results = results

    else:
        scope_status = "no_evidence"

        scope_message = (
            "The question appears related to the current clinical topic, "
            "but no strong supporting evidence was found in the registered "
            "guideline."
        )

        filtered_results = results

    # -----------------------------------------------------------------------
    # 6. Return structured response
    # -----------------------------------------------------------------------

    return SearchResponse(
        query=request.query,
        results=filtered_results,
        result_count=len(filtered_results),
        evidence_found=(
            scope_status == "in_scope"
            and above_floor > 0
        ),
        scope_status=scope_status,
        scope_message=scope_message,
        embedding_model=settings.embedding_model,
        latency_ms=latency_ms,
        disclaimer=DISCLAIMER,
    )
