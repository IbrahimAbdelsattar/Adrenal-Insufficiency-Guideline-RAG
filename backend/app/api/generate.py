"""Generation endpoints for answering clinical queries via RAG with scope guardrails.

/ generate        JSON response (with response cache + graph expansion)
/ generate/stream SSE stream of answer tokens for low perceived latency

Both paths are instrumented with a `RagTrace`: every stage (guardrail,
retrieval, scope, graph expansion, cache, prompt build, LLM, citations) is
timed individually and then summarised in one `rag.trace` log line, so the
cost of an answer can be attributed without re-running it.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.config import get_settings
from backend.app.errors import PipelineError
from backend.app.generation.assembler import assemble_evidence, select_sources
from backend.app.generation.citations import validate_grounding
from backend.app.generation.client import LLMClient
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.generation.reasoning import ReasoningFilter
from backend.app.generation.service import (
    GROUNDING_FAILED_MESSAGE,
    REASONING_ONLY_MESSAGE,
    cache_get,
    cache_key,
    cache_put,
    expand_with_graph,
    log_cache,
    run_generation_pipeline,
)
from backend.app.models import DISCLAIMER, GenerateRequest, GenerateResponse
from backend.app.monitoring import REGISTRY, RagTrace, estimate_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# JSON endpoint
# ---------------------------------------------------------------------------


@router.post("/generate")
async def generate_answer(request: GenerateRequest) -> GenerateResponse:
    """Generate an answer grounded in retrieved clinical guidelines.

    Abstains immediately if the query is an adversarial prompt injection,
    out of scope, or lacks supporting evidence.
    """
    settings = get_settings()
    trace = RagTrace("generate", query=request.query, top_k=request.top_k, settings=settings)
    started = time.perf_counter()

    result = await run_generation_pipeline(request, trace, started)

    if result.status == "error":
        raise HTTPException(status_code=503, detail=result.error_detail)

    assert result.response is not None  # noqa: S101
    return result.response


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


@router.post("/generate/stream")
async def generate_answer_stream(request: GenerateRequest) -> StreamingResponse:
    """SSE-streamed generation: tokens appear as they are produced.

    Events: meta (once) -> token (repeated) -> done (once). Errors arrive as
    an `error` event so the client can surface them.
    """

    async def events():
        started = time.perf_counter()
        settings = get_settings()
        model = settings.generation_model
        trace = RagTrace(
            "generate_stream", query=request.query, top_k=request.top_k, settings=settings
        )
        first_byte_sent: float | None = None

        # Run the shared pipeline to determine the outcome
        result = await run_generation_pipeline(request, trace, started)

        # Fast-path: greeting, injection, abstention, cache hit, grounding failed, error
        # These all produce a single token event with the full answer text.
        if result.status != "ok":
            if result.status == "error":
                yield _sse("error", {"detail": result.error_detail})
                return

            resp = result.response
            if resp is None:
                yield _sse("error", {"detail": "Unknown pipeline error"})
                return

            yield _sse(
                "meta",
                {
                    "query": request.query,
                    "model": result.model or model,
                    "evidence_found": result.evidence_found,
                    "cache_hit": result.cache_hit,
                    "clarifying_questions": result.clarifying_questions,
                },
            )
            yield _sse("token", {"text": resp.answer})
            yield _sse(
                "done",
                {
                    "citations": resp.citations,
                    "latency_ms": resp.latency_ms,
                    "disclaimer": DISCLAIMER,
                    "grounding_status": resp.grounding_status,
                },
            )
            return

        # "ok" status: we need to re-run the LLM with streaming to emit tokens.
        # The pipeline already validated grounding, so we just need to produce
        # the same answer via streaming and re-validate (or trust the cache).
        # For simplicity and correctness, we re-run the LLM stream and ground-check.

        # Re-retrieve and re-expand to get the same evidence set
        try:
            settings, top_k, results, scope_status, _, filtered_results = await (
                # Import here to avoid circular dependency at module level
                __import__(
                    "backend.app.generation.service", fromlist=["retrieve_and_scope"]
                ).retrieve_and_scope(request, trace)
            )
        except Exception as exc:
            trace.set(error=str(exc), error_type=type(exc).__name__)
            trace.emit(status="error", level=logging.ERROR)
            yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
            return

        evidence_results = expand_with_graph(settings, filtered_results or results, trace)

        with trace.stage("cache_lookup", level=logging.DEBUG) as span:
            key = cache_key(request.query, top_k, evidence_results, request.history)
            cached = cache_get(key)
            span["hit"] = cached is not None
        log_cache(trace, cached is not None)

        yield _sse(
            "meta",
            {
                "query": request.query,
                "model": model,
                "evidence_found": True,
                "cache_hit": cached is not None,
                # Already computed by the status-check pass above (`result`).
                "clarifying_questions": result.clarifying_questions,
            },
        )

        if cached is not None:
            logger.info(
                "Stream response cache hit; skipping LLM call.",
                extra={"event": "cache.hit", "streaming": True},
            )
            yield _sse("token", {"text": cached["answer"]})
            yield _sse(
                "done",
                {
                    "citations": cached["citations"],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                    "grounding_status": "verified",
                },
            )
            trace.set(evidence_found=True, citations=len(cached["citations"]), cache_hit=True)
            trace.emit(status="ok_cached")
            return

        with trace.stage("prompt_build", level=logging.DEBUG) as span:
            cited_sources = select_sources(evidence_results)
            evidence_text = assemble_evidence(evidence_results)
            user_prompt = construct_user_prompt(request.query, evidence_text, request.history)
            span["sources"] = len(cited_sources)
            span["evidence_chars"] = len(evidence_text)
            span["est_prompt_tokens"] = estimate_tokens(SYSTEM_PROMPT + user_prompt)
        trace.set(sources=len(cited_sources), evidence_chars=len(evidence_text))

        client = LLMClient(settings)

        parts: list[str] = []
        visible = ReasoningFilter()
        visible_chunks: list[str] = []
        llm_started = time.perf_counter()
        try:
            async for delta in client.stream_completion(
                system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
            ):
                parts.append(delta)
                shown = visible.feed(delta)
                if shown:
                    if first_byte_sent is None:
                        first_byte_sent = (time.perf_counter() - started) * 1000
                    visible_chunks.append(shown)
            tail = visible.flush()
            if tail:
                visible_chunks.append(tail)
        except PipelineError as exc:
            trace.set(error=str(exc), error_type="PipelineError")
            trace.emit(status="error", level=logging.ERROR)
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception as exc:
            trace.set(error=str(exc), error_type=type(exc).__name__)
            trace.emit(status="error", level=logging.ERROR)
            logger.exception(
                "Stream generation failed: %s",
                exc,
                extra={"event": "generate_stream.error", "phase": "llm"},
            )
            yield _sse("error", {"detail": f"LLM Answer Generation failed: {exc}"})
            return
        finally:
            llm_ms = (time.perf_counter() - llm_started) * 1000
            trace.stages["llm"] = round(llm_ms, 2)
            REGISTRY.observe("generate_stream.llm", llm_ms)

        answer = _finalize_answer_stream(parts, trace)
        if answer is None:
            yield _sse("error", {"detail": REASONING_ONLY_MESSAGE})
            return

        # Grounding gate
        with trace.stage("citations", level=logging.DEBUG) as span:
            grounding = validate_grounding(answer, cited_sources)
            span["resolved"] = len(grounding.citations)
            span["grounding_status"] = grounding.status
            span["grounding_reason"] = grounding.reason

        if grounding.status != "verified":
            logger.warning(
                "Streamed answer failed grounding validation: reason=%s "
                "invalid_markers=%s unsupported_claims=%d",
                grounding.reason,
                grounding.invalid_markers,
                len(grounding.unsupported_claims),
                extra={
                    "event": "grounding.failed",
                    "reason": grounding.reason,
                    "invalid_markers": grounding.invalid_markers,
                    "unsupported_claims": grounding.unsupported_claims,
                    "sources": len(cited_sources),
                    "answer_chars": len(answer),
                    "streaming": True,
                },
            )
            _log_stream_llm_result(trace, client, answer, [])
            trace.set(evidence_found=True, grounding_status="failed")
            yield _sse("token", {"text": GROUNDING_FAILED_MESSAGE})
            yield _sse(
                "done",
                {
                    "citations": [],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                    "grounding_status": "failed",
                },
            )
            trace.emit(status="abstained_grounding_failed")
            return

        citations = grounding.citations
        cache_put(
            key,
            {
                "answer": answer,
                "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in citations],
                "model": model,
            },
        )

        _log_stream_llm_result(trace, client, answer, citations)
        trace.set(
            evidence_found=True,
            grounding_status="verified",
            first_visible_token_ms=round(first_byte_sent, 2)
            if first_byte_sent is not None
            else None,
        )

        full_text = "".join(visible_chunks)
        if full_text:
            yield _sse("token", {"text": full_text})

        yield _sse(
            "done",
            {
                "citations": citations,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "disclaimer": DISCLAIMER,
                "grounding_status": "verified",
            },
        )
        trace.emit(status="ok")

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Stream helpers (local to this module)
# ---------------------------------------------------------------------------


def _finalize_answer_stream(parts: list[str], trace: RagTrace) -> str | None:
    """Finalize a streamed answer (same logic as service._finalize_answer)."""
    from backend.app.generation.citations import strip_trailing_disclaimer
    from backend.app.generation.reasoning import strip_reasoning

    raw = "".join(parts)
    answer = strip_reasoning(raw)
    if not answer:
        trace.set(reasoning_only=True, raw_chars=len(raw))
        trace.emit(status="error_reasoning_only", level=logging.ERROR)
        return None
    cleaned = strip_trailing_disclaimer(answer.strip())
    return cleaned or None


def _log_stream_llm_result(
    trace: RagTrace, client: LLMClient, answer: str, citations: list[dict]
) -> None:
    """Log LLM telemetry for the stream path."""
    trace.set(
        model=get_settings().generation_model,
        llm_ms=round(client.last_latency_ms, 2),
        llm_ttft_ms=round(client.last_ttft_ms, 2) if client.last_ttft_ms is not None else None,
        llm_attempts=client.last_attempts,
        finish_reason=client.last_finish_reason,
        answer_chars=len(answer),
        citations=len(citations),
        **{k: v for k, v in client.last_usage.items() if v is not None},
    )
