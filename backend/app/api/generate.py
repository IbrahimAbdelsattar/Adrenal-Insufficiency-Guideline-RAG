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
from backend.app.generation.citations import (
    strip_trailing_disclaimer,
    validate_grounding,
)
from backend.app.generation.client import LLMClient
from backend.app.generation.guardrails import (
    detect_prompt_injection,
    is_greeting,
)
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.generation.reasoning import ReasoningFilter, strip_reasoning
from backend.app.generation.service import (
    GROUNDING_FAILED_MESSAGE,
    INJECTION_REFUSAL_MESSAGE,
    REASONING_ONLY_MESSAGE,
    cache_get,
    cache_key,
    cache_put,
    expand_with_graph,
    log_cache,
    retrieve_and_scope,
    run_generation_pipeline,
)
from backend.app.models import DISCLAIMER, GenerateRequest, GenerateResponse
from backend.app.monitoring import RagTrace, estimate_tokens

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

        # ------------------------------------------------------------------
        # Stage 0: Greeting guardrail
        # ------------------------------------------------------------------
        if is_greeting(request.query):
            from backend.app.generation.guardrails import GREETING_RESPONSE_AR, GREETING_RESPONSE_EN

            is_ar = any("\u0600" <= c <= "\u06ff" for c in request.query)
            greeting_text = GREETING_RESPONSE_AR if is_ar else GREETING_RESPONSE_EN
            yield _sse(
                "meta",
                {
                    "query": request.query,
                    "model": model,
                    "evidence_found": True,
                    "cache_hit": False,
                },
            )
            yield _sse("token", {"text": greeting_text})
            yield _sse(
                "done",
                {
                    "citations": [],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                    "grounding_status": "verified",
                },
            )
            trace.set(evidence_found=True, citations=0)
            trace.emit(status="ok_greeting")
            return

        # ------------------------------------------------------------------
        # Stage 0.5: Prompt injection guardrail
        # ------------------------------------------------------------------
        with trace.stage("guardrail", level=logging.DEBUG) as span:
            injected = detect_prompt_injection(request.query)
            span["injection_detected"] = injected

        if injected:
            logger.warning(
                "Prompt injection detected on stream; refusing to generate.",
                extra={"event": "guardrail.injection", "query_chars": len(request.query)},
            )
            yield _sse(
                "meta",
                {
                    "query": request.query,
                    "model": model,
                    "evidence_found": False,
                    "cache_hit": False,
                },
            )
            yield _sse("token", {"text": INJECTION_REFUSAL_MESSAGE})
            yield _sse(
                "done",
                {
                    "citations": [],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                    "grounding_status": "abstained",
                },
            )
            trace.set(refusal="prompt_injection", evidence_found=False)
            trace.emit(status="refused_injection")
            return

        # ------------------------------------------------------------------
        # Stage 1: Retrieve + scope
        # ------------------------------------------------------------------
        try:
            settings, top_k, results, scope_status, _, filtered_results = await retrieve_and_scope(
                request, trace
            )
        except PipelineError as exc:
            trace.set(error=str(exc), error_type="PipelineError")
            trace.emit(status="error", level=logging.ERROR)
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception as exc:
            trace.set(error=str(exc), error_type=type(exc).__name__)
            trace.emit(status="error", level=logging.ERROR)
            logger.exception(
                "Stream retrieval failed: %s",
                exc,
                extra={"event": "generate_stream.error", "phase": "retrieval"},
            )
            yield _sse("error", {"detail": f"Retrieval failed: {exc}"})
            return

        # ------------------------------------------------------------------
        # Stage 2: Abstention paths
        # ------------------------------------------------------------------
        from backend.app.generation.citations import should_abstain
        from backend.app.retrieval.scope import NO_EVIDENCE_MESSAGE, OUT_OF_SCOPE_MESSAGE

        if scope_status in ("out_of_scope", "no_evidence") or should_abstain(results):
            if scope_status == "out_of_scope":
                answer = OUT_OF_SCOPE_MESSAGE
            else:
                answer = f"{NO_EVIDENCE_MESSAGE} Please try rephrasing or broadening your clinical query."
            yield _sse(
                "meta",
                {
                    "query": request.query,
                    "model": model,
                    "evidence_found": False,
                    "cache_hit": False,
                },
            )
            yield _sse("token", {"text": answer})
            yield _sse(
                "done",
                {
                    "citations": [],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                    "grounding_status": "abstained",
                },
            )
            trace.set(evidence_found=False, abstained=True, abstain_rule=scope_status)
            trace.emit(status=f"abstained_{scope_status}")
            return

        # ------------------------------------------------------------------
        # Stage 3: Graph expansion
        # ------------------------------------------------------------------
        evidence_results = expand_with_graph(settings, filtered_results or results, trace)

        # ------------------------------------------------------------------
        # Stage 4: Cache lookup
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Stage 5: Prompt assembly + LLM streaming
        # ------------------------------------------------------------------
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
            from backend.app.monitoring import REGISTRY

            llm_ms = (time.perf_counter() - llm_started) * 1000
            trace.stages["llm"] = round(llm_ms, 2)
            REGISTRY.observe("generate_stream.llm", llm_ms)

        # ------------------------------------------------------------------
        # Stage 6: Finalize + grounding
        # ------------------------------------------------------------------
        raw = "".join(parts)
        answer = strip_reasoning(raw)
        if not answer:
            trace.set(reasoning_only=True, raw_chars=len(raw))
            trace.emit(status="error_reasoning_only", level=logging.ERROR)
            yield _sse("error", {"detail": REASONING_ONLY_MESSAGE})
            return
        answer = strip_trailing_disclaimer(answer.strip()) or ""

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
            _log_stream_llm(trace, client, answer, [])
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

        # ------------------------------------------------------------------
        # Stage 7: Cache + emit
        # ------------------------------------------------------------------
        citations = grounding.citations
        cache_put(
            key,
            {
                "answer": answer,
                "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in citations],
                "model": model,
            },
        )

        _log_stream_llm(trace, client, answer, citations)
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
# Stream helpers
# ---------------------------------------------------------------------------


def _log_stream_llm(trace: RagTrace, client: LLMClient, answer: str, citations: list[dict]) -> None:
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
