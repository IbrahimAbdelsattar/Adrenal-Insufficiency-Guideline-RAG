"""Generation endpoints for answering clinical queries via RAG with scope guardrails.

/ generate        JSON response (with response cache + graph expansion)
/ generate/stream SSE stream of answer tokens for low perceived latency
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
from backend.app.generation.guardrails import detect_prompt_injection
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.generation.reasoning import ReasoningFilter, strip_reasoning
from backend.app.models import DISCLAIMER, GenerateRequest, GenerateResponse, RetrievalResult
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
    while len(_RESPONSE_CACHE) > maxsize:
        _RESPONSE_CACHE.popitem(last=False)


async def _retrieve_and_scope(request: GenerateRequest):
    """Shared first stage: retrieve candidates and classify scope."""
    settings = get_settings()
    retriever = get_shared_retriever(settings)
    top_k = request.top_k or settings.top_k
    results = await asyncio.to_thread(retriever.search, request.query, top_k)
    scope_status, scope_msg, filtered_results = classify_scope(results, settings.scope_threshold)
    return settings, top_k, results, scope_status, scope_msg, filtered_results


def _expand_with_graph(settings: Settings, results: list[RetrievalResult]):
    """Append graph-linked evidence (adjacent section / shared recommendations)."""
    if not settings.graph_expansion or not results:
        return results

    adjacency = graph.load_graph(settings.index_path)
    extra_ids = graph.pick_expansion_ids(results, adjacency, settings.graph_max_expand)
    if not extra_ids:
        return results

    extra_chunks = get_shared_store(settings).get_chunks(extra_ids)
    if not extra_chunks:
        return results

    expanded = list(results) + graph.wrap_expanded(extra_chunks, results)
    logger.info("Graph expansion added %d evidence chunk(s)", len(extra_chunks))
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
    started = time.perf_counter()

    # Stage 0: Prompt Injection / Adversarial Guardrail
    if detect_prompt_injection(request.query):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
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
            request
        )

        # 2. Apply scope classification guardrail
        if scope_status in ("out_of_scope", "no_evidence") or should_abstain(results):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _abstention_response(request, scope_status, elapsed_ms)

        # 3. Expand evidence with graph-linked chunks (lightweight Graph RAG)
        evidence_results = _expand_with_graph(settings, filtered_results or results)

        # 4. Response cache: identical query + identical evidence
        key = _cache_key(request.query, top_k, evidence_results)
        cached = _cache_get(key)
        if cached is not None:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("Response cache hit for query=%r", request.query)
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
        cited_sources = select_sources(evidence_results)
        evidence_text = assemble_evidence(evidence_results)
        user_prompt = construct_user_prompt(request.query, evidence_text)

        client = LLMClient(settings)
        raw_answer = await client.generate_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        answer = _finalize_answer(raw_answer)
        if answer is None:
            raise PipelineError(REASONING_ONLY_MESSAGE)

        # 6. Extract and map citations
        citations = resolve_citations(answer, cited_sources)
        _cache_put(key, {"answer": answer, "citations": citations}, settings.response_cache_size)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

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
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Generation failed: %s", exc)
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

        # Stage 0: Prompt Injection / Adversarial Guardrail
        if detect_prompt_injection(request.query):
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
            return

        try:
            settings, top_k, results, scope_status, _, filtered_results = await _retrieve_and_scope(
                request
            )
        except PipelineError as exc:
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception as exc:
            logger.error("Stream retrieval failed: %s", exc)
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
            return

        evidence_results = _expand_with_graph(settings, filtered_results or results)
        key = _cache_key(request.query, top_k, evidence_results)
        cached = _cache_get(key)

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
            logger.info("Stream response cache hit for query=%r", request.query)
            yield _sse("token", {"text": cached["answer"]})
            yield _sse(
                "done",
                {
                    "citations": cached["citations"],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "disclaimer": DISCLAIMER,
                },
            )
            return

        cited_sources = select_sources(evidence_results)
        evidence_text = assemble_evidence(evidence_results)
        user_prompt = construct_user_prompt(request.query, evidence_text)
        client = LLMClient(settings)

        parts: list[str] = []
        # `parts` keeps the raw completion so the final answer is computed the
        # same way as the non-streaming path; the filter only decides what the
        # user is allowed to watch arrive, so reasoning never renders live.
        visible = ReasoningFilter()
        try:
            async for delta in client.stream_completion(
                system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
            ):
                parts.append(delta)
                shown = visible.feed(delta)
                if shown:
                    yield _sse("token", {"text": shown})
            tail = visible.flush()
            if tail:
                yield _sse("token", {"text": tail})
        except PipelineError as exc:
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception as exc:
            logger.error("Stream generation failed: %s", exc)
            yield _sse("error", {"detail": f"LLM Answer Generation failed: {exc}"})
            return

        answer = _finalize_answer("".join(parts))
        if answer is None:
            yield _sse("error", {"detail": REASONING_ONLY_MESSAGE})
            return
        citations = resolve_citations(answer, cited_sources)
        _cache_put(key, {"answer": answer, "citations": citations}, settings.response_cache_size)

        yield _sse(
            "done",
            {
                "citations": citations,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "disclaimer": DISCLAIMER,
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
