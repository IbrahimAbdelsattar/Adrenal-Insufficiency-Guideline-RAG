"""Generation endpoints for answering clinical queries via RAG with scope guardrails.

/ generate        JSON response (with response cache + graph expansion)
/ generate/stream SSE stream of answer tokens for low perceived latency

Both paths are instrumented with a `RagTrace`: every stage (guardrail,
retrieval, scope, graph expansion, cache, prompt build, LLM, citations) is
timed individually and then summarised in one `rag.trace` log line, so the
cost of an answer can be attributed without re-running it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app import graph
from backend.app.config import Settings, get_settings
from backend.app.errors import PipelineError
from backend.app.generation.assembler import assemble_evidence, select_sources
from backend.app.generation.citations import (
    resolve_citations,
    should_abstain,
    strip_trailing_disclaimer,
)
from backend.app.generation.client import LLMClient
from backend.app.generation.guardrails import (
    GREETING_RESPONSE_AR,
    GREETING_RESPONSE_EN,
    detect_prompt_injection,
    is_greeting,
)
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.generation.reasoning import ReasoningFilter, strip_reasoning
from backend.app.models import DISCLAIMER, GenerateRequest, GenerateResponse, RetrievalResult
from backend.app.monitoring import REGISTRY, RagTrace, estimate_tokens
from backend.app.retrieval.factory import get_shared_retriever, get_shared_store
from backend.app.retrieval.scope import (
    NO_EVIDENCE_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    classify_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])

# LRU response cache: same query + same retrieved evidence => same answer,
# so repeat questions cost zero tokens and return in milliseconds.
_RESPONSE_CACHE: OrderedDict[str, dict] = OrderedDict()


def _cache_key(query: str, top_k: int, results: list[RetrievalResult]) -> str:
    ids = "+".join(r.chunk.chunk_id for r in results)
    return f"{top_k}|{query.strip().lower()}|{ids}"


def _cache_get(key: str) -> dict | None:
    entry = _RESPONSE_CACHE.get(key)
    if entry is not None:
        _RESPONSE_CACHE.move_to_end(key)
    return entry


def _cache_put(key: str, entry: dict, maxsize: int) -> None:
    _RESPONSE_CACHE[key] = entry
    _RESPONSE_CACHE.move_to_end(key)
    evicted = 0
    while len(_RESPONSE_CACHE) > maxsize:
        _RESPONSE_CACHE.popitem(last=False)
        evicted += 1
    if evicted:
        logger.debug(
            "Response cache evicted %d entr%s (size=%d/%d)",
            evicted,
            "y" if evicted == 1 else "ies",
            len(_RESPONSE_CACHE),
            maxsize,
            extra={
                "event": "cache.evict",
                "evicted": evicted,
                "size": len(_RESPONSE_CACHE),
                "maxsize": maxsize,
            },
        )


def _log_cache(trace: RagTrace, hit: bool) -> None:
    REGISTRY.increment("generate.cache.hit" if hit else "generate.cache.miss")
    trace.set(cache_hit=hit, cache_size=len(_RESPONSE_CACHE))


async def _retrieve_and_scope(request: GenerateRequest, trace: RagTrace):
    """Shared first stage: retrieve candidates and classify scope."""
    settings = get_settings()
    retriever = get_shared_retriever(settings)
    top_k = request.top_k or settings.top_k

    with trace.stage(
        "retrieval", top_k=top_k, retriever_type=settings.retriever_type
    ) as span:
        results = await asyncio.to_thread(retriever.search, request.query, top_k)
        span["results"] = len(results)
        span["top_relevance"] = round(results[0].absolute_relevance, 4) if results else 0.0

    trace.record_retrieval(results)

    with trace.stage("scope", scope_threshold=settings.scope_threshold) as span:
        scope_status, scope_msg, filtered_results = classify_scope(
            results, settings.scope_threshold
        )
        span["scope_status"] = scope_status
        span["kept"] = len(filtered_results)

    trace.set(scope_status=scope_status)
    REGISTRY.increment(f"generate.scope.{scope_status}")
    return settings, top_k, results, scope_status, scope_msg, filtered_results


def _expand_with_graph(
    settings: Settings, results: list[RetrievalResult], trace: RagTrace | None = None
):
    """Append graph-linked evidence (adjacent section / shared recommendations)."""
    if not settings.graph_expansion or not results:
        if trace is not None:
            trace.set(graph_expanded=0)
        return results

    def _run() -> list[RetrievalResult]:
        adjacency = graph.load_graph(settings.index_path)
        extra_ids = graph.pick_expansion_ids(results, adjacency, settings.graph_max_expand)
        if not extra_ids:
            return list(results)

        extra_chunks = get_shared_store(settings).get_chunks(extra_ids)
        if not extra_chunks:
            return list(results)

        expanded = list(results) + graph.wrap_expanded(extra_chunks, results)
        logger.info(
            "Graph expansion added %d evidence chunk(s)",
            len(extra_chunks),
            extra={
                "event": "graph.expansion",
                "added": len(extra_chunks),
                "added_chunk_ids": [c.chunk_id for c in extra_chunks],
                "max_expand": settings.graph_max_expand,
            },
        )
        return expanded

    if trace is None:
        return _run()

    with trace.stage("graph_expansion", max_expand=settings.graph_max_expand) as span:
        expanded = _run()
        span["added"] = len(expanded) - len(results)

    trace.set(graph_expanded=len(expanded) - len(results), evidence_chunks=len(expanded))
    return expanded


def _abstention_response(
    request: GenerateRequest, scope_status: str, elapsed_ms: int
) -> GenerateResponse:
    if scope_status == "out_of_scope":
        answer = OUT_OF_SCOPE_MESSAGE
    else:
        answer = f"{NO_EVIDENCE_MESSAGE} Please try rephrasing or broadening your clinical query."
    return GenerateResponse(
        query=request.query,
        answer=answer,
        citations=[],
        evidence_found=False,
        disclaimer=DISCLAIMER,
        model=get_settings().generation_model,
        latency_ms=elapsed_ms,
    )


REASONING_ONLY_MESSAGE = (
    "The model returned only its internal reasoning and no answer, which usually "
    "means GENERATION_MAX_TOKENS is too low for a reasoning model. Raise it, or "
    "set GENERATION_MODEL to a non-reasoning model."
)


def _finalize_answer(raw: str) -> str | None:
    """Clean a raw completion into a displayable answer.

    Chain-of-thought is stripped before anything else: it is not an answer, and
    it names sources the model goes on to reject, so leaving it in would both
    show a clinician the model's scratchpad and fabricate citations from it.

    Returns None when nothing survives -- the model spent its whole budget
    thinking. Callers must surface an error rather than render the reasoning.
    """
    answer = strip_reasoning(raw)
    if not answer:
        return None
    return strip_trailing_disclaimer(answer.strip()) or None


def _log_llm_result(trace: RagTrace, client: LLMClient, answer: str, citations: list[dict]) -> None:
    """Fold the client's per-call telemetry into the request trace."""
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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


INJECTION_REFUSAL_MESSAGE = (
    "This request cannot be processed. Eva AI only answers clinical questions "
    "about adrenal insufficiency based on NICE NG243. Please rephrase your question."
)


@router.post("/generate")
async def generate_answer(request: GenerateRequest) -> GenerateResponse:
    """Generate an answer grounded in retrieved clinical guidelines.

    Abstains immediately if the query is an adversarial prompt injection,
    out of scope, or lacks supporting evidence.
    """
    settings = get_settings()
    trace = RagTrace("generate", query=request.query, top_k=request.top_k, settings=settings)
    started = time.perf_counter()

    # Stage 0: Conversational Greeting / Capability Inquiry
    if is_greeting(request.query):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        is_ar = any("\u0600" <= c <= "\u06FF" for c in request.query)
        greeting_text = GREETING_RESPONSE_AR if is_ar else GREETING_RESPONSE_EN
        trace.set(evidence_found=True, citations=0)
        trace.emit(status="ok_greeting")
        return GenerateResponse(
            query=request.query,
            answer=greeting_text,
            citations=[],
            evidence_found=True,
            disclaimer=DISCLAIMER,
            model=settings.generation_model,
            latency_ms=elapsed_ms,
        )

    # Stage 0.5: Prompt Injection / Adversarial Guardrail
    with trace.stage("guardrail", level=logging.DEBUG) as span:
        injected = detect_prompt_injection(request.query)
        span["injection_detected"] = injected


    if injected:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "Prompt injection detected; refusing to generate.",
            extra={"event": "guardrail.injection", "query_chars": len(request.query)},
        )
        trace.set(refusal="prompt_injection", evidence_found=False)
        trace.emit(status="refused_injection")
        return GenerateResponse(
            query=request.query,
            answer=INJECTION_REFUSAL_MESSAGE,
            citations=[],
            evidence_found=False,
            disclaimer=DISCLAIMER,
            model=settings.generation_model,
            latency_ms=elapsed_ms,
        )

    try:
        # 1. Retrieve candidate evidence (shared retriever: no per-request rebuild)
        settings, top_k, results, scope_status, _, filtered_results = await _retrieve_and_scope(
            request, trace
        )

        # 2. Apply scope classification guardrail
        abstain = should_abstain(results)
        if scope_status in ("out_of_scope", "no_evidence") or abstain:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            trace.set(evidence_found=False, abstained=True, abstain_rule=scope_status)
            trace.emit(status=f"abstained_{scope_status}")
            return _abstention_response(request, scope_status, elapsed_ms)

        # 3. Expand evidence with graph-linked chunks (lightweight Graph RAG)
        evidence_results = _expand_with_graph(settings, filtered_results or results, trace)

        # 4. Response cache: identical query + identical evidence
        with trace.stage("cache_lookup", level=logging.DEBUG) as span:
            key = _cache_key(request.query, top_k, evidence_results)
            cached = _cache_get(key)
            span["hit"] = cached is not None
        _log_cache(trace, cached is not None)

        if cached is not None:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "Response cache hit; skipping LLM call.",
                extra={"event": "cache.hit", "latency_ms": elapsed_ms},
            )
            trace.set(evidence_found=True, citations=len(cached["citations"]))
            trace.emit(status="ok_cached")
            return GenerateResponse(
                query=request.query,
                answer=cached["answer"],
                citations=cached["citations"],
                evidence_found=True,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
                cache_hit=True,
            )

        # 5. Assemble evidence context and synthesize via OmniRoute
        # cited_sources is what the LLM actually sees numbered [Source 1..N];
        # citations must resolve against it, not the unfiltered result list.
        with trace.stage("prompt_build", level=logging.DEBUG) as span:
            cited_sources = select_sources(evidence_results)
            evidence_text = assemble_evidence(evidence_results)
            user_prompt = construct_user_prompt(request.query, evidence_text, request.history)
            span["sources"] = len(cited_sources)
            span["evidence_chars"] = len(evidence_text)
            span["est_prompt_tokens"] = estimate_tokens(SYSTEM_PROMPT + user_prompt)
        trace.set(sources=len(cited_sources), evidence_chars=len(evidence_text))


        client = LLMClient(settings)
        with trace.stage("llm"):
            raw_answer = await client.generate_completion(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        answer = _finalize_answer(raw_answer)
        if answer is None:
            trace.set(reasoning_only=True, raw_chars=len(raw_answer))
            raise PipelineError(REASONING_ONLY_MESSAGE)

        # 6. Extract and map citations
        with trace.stage("citations", level=logging.DEBUG) as span:
            citations = resolve_citations(answer, cited_sources)
            span["resolved"] = len(citations)
        # Cited nothing while evidence was supplied: the answer may be
        # ungrounded, which is exactly the failure clinicians must see.
        if not citations:
            logger.warning(
                "Answer produced no resolvable citations despite %d source(s).",
                len(cited_sources),
                extra={
                    "event": "citations.empty",
                    "sources": len(cited_sources),
                    "answer_chars": len(answer),
                },
            )

        _cache_put(key, {"answer": answer, "citations": citations}, settings.response_cache_size)
        _log_llm_result(trace, client, answer, citations)
        trace.set(evidence_found=True)
        elapsed_ms = trace.emit(status="ok")

        return GenerateResponse(
            query=request.query,
            answer=answer,
            citations=citations,
            evidence_found=True,
            disclaimer=DISCLAIMER,
            model=settings.generation_model,
            latency_ms=elapsed_ms,
        )

    except PipelineError as exc:
        trace.set(error=str(exc), error_type="PipelineError")
        trace.emit(status="error", level=logging.ERROR)
        logger.error(
            "Generation pipeline error: %s",
            exc,
            extra={"event": "generate.error", "error_type": "PipelineError"},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        trace.set(error=str(exc), error_type=type(exc).__name__)
        trace.emit(status="error", level=logging.ERROR)
        logger.exception(
            "Generation failed: %s",
            exc,
            extra={"event": "generate.error", "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=503, detail=f"LLM Answer Generation failed: {exc}") from exc


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

        # Stage 0: Conversational Greeting / Capability Inquiry
        if is_greeting(request.query):
            is_ar = any("\u0600" <= c <= "\u06FF" for c in request.query)
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
                },
            )
            trace.set(evidence_found=True, citations=0)
            trace.emit(status="ok_greeting")
            return

        # Stage 0.5: Prompt Injection / Adversarial Guardrail
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
                },
            )
            trace.set(refusal="prompt_injection", evidence_found=False)
            trace.emit(status="refused_injection")
            return

        try:
            settings, top_k, results, scope_status, _, filtered_results = await _retrieve_and_scope(
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

        # Abstention paths short-circuit with a single token event.
        if scope_status in ("out_of_scope", "no_evidence") or should_abstain(results):
            response = _abstention_response(request, scope_status, 0)
            yield _sse(
                "meta",
                {
                    "query": request.query,
                    "model": model,
                    "evidence_found": False,
                    "cache_hit": False,
                },
            )
            yield _sse("token", {"text": response.answer})
            yield _sse(
                "done",
                {
                    "citations": [],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                },
            )
            trace.set(evidence_found=False, abstained=True, abstain_rule=scope_status)
            trace.emit(status=f"abstained_{scope_status}")
            return

        evidence_results = _expand_with_graph(settings, filtered_results or results, trace)

        with trace.stage("cache_lookup", level=logging.DEBUG) as span:
            key = _cache_key(request.query, top_k, evidence_results)
            cached = _cache_get(key)
            span["hit"] = cached is not None
        _log_cache(trace, cached is not None)

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
                },
            )
            trace.set(evidence_found=True, citations=len(cached["citations"]))
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
        # `parts` keeps the raw completion so the final answer is computed the
        # same way as the non-streaming path; the filter only decides what the
        # user is allowed to watch arrive, so reasoning never renders live.
        visible = ReasoningFilter()
        llm_started = time.perf_counter()
        try:
            async for delta in client.stream_completion(
                system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
            ):
                parts.append(delta)
                shown = visible.feed(delta)
                if shown:
                    if first_byte_sent is None:
                        # What the user perceives: the first token that is
                        # actually rendered, after reasoning has been filtered.
                        first_byte_sent = (time.perf_counter() - started) * 1000
                        REGISTRY.observe("generate_stream.first_visible_token", first_byte_sent)
                        logger.info(
                            "First visible token after %.0f ms.",
                            first_byte_sent,
                            extra={
                                "event": "stream.first_visible_token",
                                "duration_ms": round(first_byte_sent, 2),
                            },
                        )
                    yield _sse("token", {"text": shown})
            tail = visible.flush()
            if tail:
                yield _sse("token", {"text": tail})
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

        answer = _finalize_answer("".join(parts))
        if answer is None:
            trace.set(reasoning_only=True, raw_chars=sum(len(p) for p in parts))
            trace.emit(status="error_reasoning_only", level=logging.ERROR)
            yield _sse("error", {"detail": REASONING_ONLY_MESSAGE})
            return

        with trace.stage("citations", level=logging.DEBUG) as span:
            citations = resolve_citations(answer, cited_sources)
            span["resolved"] = len(citations)
        if not citations:
            logger.warning(
                "Streamed answer produced no resolvable citations despite %d source(s).",
                len(cited_sources),
                extra={
                    "event": "citations.empty",
                    "sources": len(cited_sources),
                    "answer_chars": len(answer),
                },
            )

        _cache_put(key, {"answer": answer, "citations": citations}, settings.response_cache_size)
        _log_llm_result(trace, client, answer, citations)
        trace.set(
            evidence_found=True,
            first_visible_token_ms=round(first_byte_sent, 2)
            if first_byte_sent is not None
            else None,
        )

        yield _sse(
            "done",
            {
                "citations": citations,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "disclaimer": DISCLAIMER,
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
