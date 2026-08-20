"""Shared generation pipeline used by both JSON and SSE endpoints.

Encapsulates every stage -- greeting guard, injection guard, retrieval,
scope classification, graph expansion, response cache, prompt assembly,
LLM call, and grounding validation -- so the transport layer only needs
to decide *how* to deliver the result, not *how* to compute it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app import graph
from backend.app.config import Settings, get_settings
from backend.app.errors import PipelineError
from backend.app.generation.assembler import assemble_evidence, select_sources
from backend.app.generation.citations import (
    should_abstain,
    strip_trailing_disclaimer,
    validate_grounding,
)
from backend.app.generation.clarification import suggest_clarifying_questions
from backend.app.generation.client import LLMClient
from backend.app.generation.guardrails import (
    DOSAGE_REFUSAL_MESSAGE_AR,
    DOSAGE_REFUSAL_MESSAGE_EN,
    GREETING_RESPONSE_AR,
    GREETING_RESPONSE_EN,
    detect_prompt_injection,
    is_dosage_or_medication_query,
    is_greeting,
)
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.generation.reasoning import strip_reasoning
from backend.app.generation.risk_classifier import classify_input_risk
from backend.app.models import (
    DISCLAIMER,
    GenerateRequest,
    GenerateResponse,
    InputRiskAssessment,
    RetrievalResult,
)
from backend.app.monitoring import REGISTRY, RagTrace, estimate_tokens, traceable
from backend.app.monitoring.langsmith import scrub_trace_value
from backend.app.retrieval.cache import TTLLRUCache, normalize_query
from backend.app.retrieval.factory import get_shared_retriever, get_shared_store
from backend.app.retrieval.scope import (
    NO_EVIDENCE_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    classify_scope,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GROUNDING_FAILED_MESSAGE = (
    "Eva AI generated a response but could not verify that every clinical claim in it "
    "-- doses, routes, timing, thresholds, or emergency instructions -- is directly "
    "supported by a cited passage in the retrieved guideline. Rather than show an "
    "answer that might state an unverified dose or instruction, it has been withheld. "
    "Please try rephrasing your question, or consult the guideline directly."
)

REASONING_ONLY_MESSAGE = (
    "The model returned only its internal reasoning and no answer, which usually "
    "means GENERATION_MAX_TOKENS is too low for a reasoning model. Raise it, or "
    "set GENERATION_MODEL to a non-reasoning model."
)

INJECTION_REFUSAL_MESSAGE = (
    "This request cannot be processed. Eva AI only answers clinical questions "
    "about adrenal insufficiency based on NICE NG243. Please rephrase your question."
)

# ---------------------------------------------------------------------------
# Response cache
# ---------------------------------------------------------------------------

_RESPONSE_CACHE: TTLLRUCache[str, dict] = TTLLRUCache(
    maxsize=get_settings().response_cache_size,
    ttl_seconds=get_settings().cache_ttl_seconds,
    manifest_path=get_settings().index_dir / "manifest.json",
    name="generation_response_cache",
)


def cache_key(
    query: str,
    top_k: int,
    results: list[RetrievalResult],
    history: list[dict] | None = None,
) -> str:
    norm_q = normalize_query(query)
    ids = "+".join(r.chunk.chunk_id for r in results)
    hist_suffix = ""
    if history:
        hist_parts = [
            f"{h.get('role', '')}:{normalize_query(h.get('content', ''))}"
            for h in history[-4:]
            if h.get("content")
        ]
        if hist_parts:
            hist_suffix = "|hist:" + "+".join(hist_parts)
    return f"{top_k}|{norm_q}|{ids}{hist_suffix}"


def cache_get(key: str) -> dict | None:
    return _RESPONSE_CACHE.get(key)


def cache_put(key: str, entry: dict) -> None:
    _RESPONSE_CACHE.put(key, entry)


def cache_clear() -> None:
    _RESPONSE_CACHE.clear()


def log_cache(trace: RagTrace, hit: bool) -> None:
    REGISTRY.increment("generate.cache.hit" if hit else "generate.cache.miss")
    trace.set(cache_hit=hit, cache_size=len(_RESPONSE_CACHE))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_llm_result(trace: RagTrace, client: LLMClient, answer: str, citations: list[dict]) -> None:
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


def _finalize_answer(raw: str) -> str | None:
    """Clean a raw completion into a displayable answer.

    Returns None when nothing survives (the model spent its whole budget
    thinking). Callers must surface an error rather than render the reasoning.
    """
    answer = strip_reasoning(raw)
    if not answer:
        return None
    answer_stripped = strip_trailing_disclaimer(answer.strip()) or ""
    if not answer_stripped:
        return None

    from backend.app.generation.prompt import (
        PHARMACOLOGICAL_DISCLAIMER,
        contains_pharmacological_content,
    )

    if contains_pharmacological_content(answer_stripped):
        if "Clinical Disclaimer" not in answer_stripped:
            answer_stripped += PHARMACOLOGICAL_DISCLAIMER

    return answer_stripped


def _abstention_response(
    request: GenerateRequest,
    scope_status: str,
    elapsed_ms: int,
    risk_assessment: InputRiskAssessment | None = None,
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
        grounding_status="abstained",
        risk_assessment=risk_assessment,
    )


# ---------------------------------------------------------------------------
# LangSmith trace shaping
#
# process_inputs/process_outputs keep raw GenerateRequest/RagTrace objects
# (and their query text) out of what actually gets serialized and sent to
# LangSmith -- only the scrubbed, summarized fields below leave the process.
# ---------------------------------------------------------------------------


def _reduce_retrieve_inputs(inputs: dict) -> dict:
    request = inputs.get("request")
    return {
        "query": scrub_trace_value(getattr(request, "query", "")),
        "top_k": getattr(request, "top_k", None),
    }


def _reduce_retrieve_outputs(outputs: Any) -> dict:
    _settings, top_k, results, scope_status, _scope_msg, filtered = outputs
    return {
        "top_k": top_k,
        "scope_status": scope_status,
        "retrieved_chunks": len(results),
        "filtered_chunks": len(filtered),
        "chunk_ids": [r.chunk.chunk_id for r in results[:10]],
    }


def _reduce_pipeline_inputs(inputs: dict) -> dict:
    request = inputs.get("request")
    history = getattr(request, "history", None) or []
    return {
        "query": scrub_trace_value(getattr(request, "query", "")),
        "top_k": getattr(request, "top_k", None),
        "history_len": len(history),
    }


def _reduce_pipeline_outputs(result: Any) -> dict:
    return {
        "status": getattr(result, "status", None),
        "evidence_found": getattr(result, "evidence_found", None),
        "cache_hit": getattr(result, "cache_hit", None),
        "citations": len(getattr(result, "citations", None) or []),
        "latency_ms": getattr(result, "latency_ms", None),
        "answer": scrub_trace_value(getattr(result, "answer", "")),
    }


# ---------------------------------------------------------------------------
# Shared pipeline stages
# ---------------------------------------------------------------------------


@traceable(
    run_type="retriever",
    name="rag.retrieve_and_scope",
    process_inputs=_reduce_retrieve_inputs,
    process_outputs=_reduce_retrieve_outputs,
)
async def retrieve_and_scope(
    request: GenerateRequest, trace: RagTrace
) -> tuple[Settings, int, list[RetrievalResult], str, str, list[RetrievalResult]]:
    """Retrieve and scope chunks for a request, timing each step."""
    settings = get_settings()
    top_k = request.top_k or settings.top_k

    with trace.stage("retrieval"):
        retriever = get_shared_retriever(settings)
        if hasattr(retriever, "search_async"):
            results = await retriever.search_async(request.query, top_k=top_k)
        else:
            results = retriever.search(request.query, top_k=top_k)

    with trace.stage("scope"):
        scope_status, scope_msg, filtered_results = classify_scope(
            results, settings.scope_threshold, request.query
        )

    trace.set(
        top_k=top_k,
        retrieved_chunks=len(results),
        scope=scope_status,
    )
    return settings, top_k, results, scope_status, scope_msg, filtered_results


def expand_with_graph(
    settings: Settings,
    results: list[RetrievalResult],
    trace: RagTrace | None = None,
) -> list[RetrievalResult]:
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


# ---------------------------------------------------------------------------
# Full pipeline result (used by both JSON and SSE)
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    """Outcome of the generation pipeline.

    Transport layers (JSON / SSE) read this instead of duplicating logic.
    """

    status: str
    """One of: greeting, injection_refusal, abstained, cache_hit, ok, grounding_failed,
    reasoning_only, error."""

    response: GenerateResponse | None = None
    """Populated for status in {greeting, injection_refusal, abstained, cache_hit, ok, grounding_failed}."""

    error_detail: str | None = None
    """Populated for status=error."""

    # Fields needed by SSE to emit meta/done events without re-reading response:
    query: str = ""
    model: str = ""
    evidence_found: bool = False
    cache_hit: bool = False
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    latency_ms: int = 0
    risk_assessment: InputRiskAssessment | None = None

    # For SSE streaming: the raw accumulated parts before finalization
    raw_parts: list[str] | None = None

    # UI hint when the query is ambiguously scoped (missing age group or
    # clinical context on a dosing question). Never gates generation.
    clarifying_questions: list[str] = field(default_factory=list)


@traceable(
    run_type="chain",
    name="rag.generation_pipeline",
    process_inputs=_reduce_pipeline_inputs,
    process_outputs=_reduce_pipeline_outputs,
)
async def run_generation_pipeline(
    request: GenerateRequest,
    trace: RagTrace,
    started: float,
) -> GenerationResult:
    """Execute the full generation pipeline and return a structured result.

    This is the single source of truth for both the JSON and SSE endpoints.
    """
    settings = get_settings()

    # Stage 0: Input Risk Classification
    risk_assessment = classify_input_risk(request.query, request.history)
    trace.set(
        risk_tier=risk_assessment.tier.value,
        is_emergency=risk_assessment.is_emergency,
    )

    # Stage 0.1: Conversational Greeting
    if is_greeting(request.query):
        is_ar = any("\u0600" <= c <= "\u06ff" for c in request.query)
        greeting_text = GREETING_RESPONSE_AR if is_ar else GREETING_RESPONSE_EN
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        trace.set(evidence_found=True, citations=0)
        trace.emit(status="ok_greeting")
        return GenerationResult(
            status="greeting",
            response=GenerateResponse(
                query=request.query,
                answer=greeting_text,
                citations=[],
                evidence_found=True,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
                grounding_status="verified",
                risk_assessment=risk_assessment,
            ),
            query=request.query,
            model=settings.generation_model,
            answer=greeting_text,
            clarifying_questions=[],  # canned greeting text, nothing to scope
            risk_assessment=risk_assessment,
        )

    # Stage 0.5: Prompt Injection Guard
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
        return GenerationResult(
            status="injection_refusal",
            response=GenerateResponse(
                query=request.query,
                answer=INJECTION_REFUSAL_MESSAGE,
                citations=[],
                evidence_found=False,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
                grounding_status="abstained",
                risk_assessment=risk_assessment,
            ),
            query=request.query,
            model=settings.generation_model,
            evidence_found=False,
            clarifying_questions=[],  # refused outright, nothing to scope
            risk_assessment=risk_assessment,
        )

    # Stage 0.7: Dosage & Medication Query Guard
    with trace.stage("guardrail_dosage", level=logging.DEBUG) as span:
        is_dosage_query = is_dosage_or_medication_query(request.query)
        span["dosage_query_detected"] = is_dosage_query

    if is_dosage_query:
        is_ar = any("\u0600" <= c <= "\u06ff" for c in request.query)
        refusal_msg = DOSAGE_REFUSAL_MESSAGE_AR if is_ar else DOSAGE_REFUSAL_MESSAGE_EN
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "Dosage or medication query detected; refusing to generate.",
            extra={"event": "guardrail.dosage_refusal", "query_chars": len(request.query)},
        )
        trace.set(refusal="dosage_refusal", evidence_found=False)
        trace.emit(status="refused_dosage")
        return GenerationResult(
            status="abstained",
            response=GenerateResponse(
                query=request.query,
                answer=refusal_msg,
                citations=[],
                evidence_found=False,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
                grounding_status="abstained",
            ),
            query=request.query,
            model=settings.generation_model,
            evidence_found=False,
            answer=refusal_msg,
            clarifying_questions=[],
        )

    try:
        # 1. Retrieve + scope
        settings, top_k, results, scope_status, _, filtered_results = await retrieve_and_scope(
            request, trace
        )

        # 2. Scope guardrail
        abstain = should_abstain(results)
        if scope_status in ("out_of_scope", "no_evidence") or abstain:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            trace.set(evidence_found=False, abstained=True, abstain_rule=scope_status)
            trace.emit(status=f"abstained_{scope_status}")
            clarifying = suggest_clarifying_questions(request.query)
            resp = _abstention_response(request, scope_status, elapsed_ms, risk_assessment)
            resp.clarifying_questions = clarifying
            return GenerationResult(
                status="abstained",
                response=resp,
                query=request.query,
                model=settings.generation_model,
                answer=resp.answer,
                clarifying_questions=clarifying,
                risk_assessment=risk_assessment,
            )

        # 3. Graph expansion
        evidence_results = expand_with_graph(settings, filtered_results or results, trace)

        # 4. Response cache
        with trace.stage("cache_lookup", level=logging.DEBUG) as span:
            key = cache_key(request.query, top_k, evidence_results, request.history)
            cached = cache_get(key)
            span["hit"] = cached is not None
        log_cache(trace, cached is not None)

        if cached is not None:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "Response cache hit; skipping LLM call.",
                extra={"event": "cache.hit", "latency_ms": elapsed_ms},
            )
            trace.set(evidence_found=True, citations=len(cached["citations"]))
            trace.emit(status="ok_cached")
            return GenerationResult(
                status="cache_hit",
                response=GenerateResponse(
                    query=request.query,
                    answer=cached["answer"],
                    citations=cached["citations"],
                    evidence_found=True,
                    disclaimer=DISCLAIMER,
                    model=cached.get("model", settings.generation_model),
                    latency_ms=elapsed_ms,
                    cache_hit=True,
                    grounding_status="verified",
                    clarifying_questions=suggest_clarifying_questions(request.query),
                    risk_assessment=risk_assessment,
                ),
                query=request.query,
                model=cached.get("model", settings.generation_model),
                evidence_found=True,
                cache_hit=True,
                answer=cached["answer"],
                citations=cached["citations"],
                latency_ms=elapsed_ms,
                clarifying_questions=suggest_clarifying_questions(request.query),
                risk_assessment=risk_assessment,
            )

        # 5. Prompt assembly + LLM call
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

        # 6. Grounding gate
        with trace.stage("citations", level=logging.DEBUG) as span:
            grounding = validate_grounding(answer, cited_sources)
            span["resolved"] = len(grounding.citations)
            span["grounding_status"] = grounding.status
            span["grounding_reason"] = grounding.reason

        if grounding.status != "verified":
            logger.warning(
                "Grounding validation failed: reason=%s invalid_markers=%s unsupported_claims=%d",
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
                },
            )
            _log_llm_result(trace, client, answer, [])
            trace.set(evidence_found=True, grounding_status="failed")
            elapsed_ms = trace.emit(status="abstained_grounding_failed")
            return GenerationResult(
                status="grounding_failed",
                response=GenerateResponse(
                    query=request.query,
                    answer=GROUNDING_FAILED_MESSAGE,
                    citations=[],
                    evidence_found=True,
                    disclaimer=DISCLAIMER,
                    model=settings.generation_model,
                    latency_ms=elapsed_ms,
                    grounding_status="failed",
                    clarifying_questions=suggest_clarifying_questions(request.query),
                    risk_assessment=risk_assessment,
                ),
                query=request.query,
                model=settings.generation_model,
                evidence_found=True,
                answer=GROUNDING_FAILED_MESSAGE,
                clarifying_questions=suggest_clarifying_questions(request.query),
                risk_assessment=risk_assessment,
            )

        citations = grounding.citations
        cache_put(
            key,
            {
                "answer": answer,
                "citations": [c.model_dump() if hasattr(c, "model_dump") else c for c in citations],
                "model": settings.generation_model,
            },
        )

        _log_llm_result(trace, client, answer, citations)
        trace.set(evidence_found=True, grounding_status="verified")
        elapsed_ms = trace.emit(status="ok")

        return GenerationResult(
            status="ok",
            response=GenerateResponse(
                query=request.query,
                answer=answer,
                citations=citations,
                evidence_found=True,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
                grounding_status="verified",
                clarifying_questions=suggest_clarifying_questions(request.query),
                risk_assessment=risk_assessment,
            ),
            query=request.query,
            model=settings.generation_model,
            evidence_found=True,
            answer=answer,
            citations=citations,
            latency_ms=elapsed_ms,
            clarifying_questions=suggest_clarifying_questions(request.query),
            risk_assessment=risk_assessment,
        )

    except PipelineError as exc:
        trace.set(error=str(exc), error_type="PipelineError")
        trace.emit(status="error", level=logging.ERROR)
        logger.error(
            "Generation pipeline error: %s",
            exc,
            extra={"event": "generate.error", "error_type": "PipelineError"},
        )
        return GenerationResult(
            status="error",
            error_detail=str(exc),
            query=request.query,
            model=settings.generation_model,
        )

    except Exception as exc:
        trace.set(error=str(exc), error_type=type(exc).__name__)
        trace.emit(status="error", level=logging.ERROR)
        logger.exception(
            "Generation failed: %s",
            exc,
            extra={"event": "generate.error", "error_type": type(exc).__name__},
        )
        return GenerationResult(
            status="error",
            error_detail=f"LLM Answer Generation failed: {exc}",
            query=request.query,
            model=settings.generation_model,
        )
