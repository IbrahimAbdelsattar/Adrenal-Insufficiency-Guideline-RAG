"""Generation endpoint for answering clinical queries via RAG with scope guardrails."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from backend.app.config import get_settings
from backend.app.errors import PipelineError
from backend.app.generation.assembler import assemble_evidence
from backend.app.generation.citations import extract_citations, should_abstain
from backend.app.generation.client import LLMClient
from backend.app.generation.prompt import SYSTEM_PROMPT, construct_user_prompt
from backend.app.models import DISCLAIMER, GenerateRequest, GenerateResponse
from backend.app.retrieval.factory import get_retriever
from backend.app.retrieval.scope import (
    NO_EVIDENCE_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    classify_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate")
async def generate_answer(request: GenerateRequest) -> GenerateResponse:
    """Generate an answer grounded in retrieved clinical guidelines.

    Abstains immediately if the query is out of scope or lacks supporting evidence.
    """
    settings = get_settings()
    started = time.perf_counter()

    try:
        # 1. Retrieve candidate evidence
        retriever = get_retriever(settings)
        top_k = request.top_k or settings.top_k
        results = retriever.search(request.query, top_k)

        # 2. Apply scope classification guardrail
        scope_status, scope_msg, filtered_results = classify_scope(
            results, settings.scope_threshold
        )

        if scope_status == "out_of_scope":
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return GenerateResponse(
                query=request.query,
                answer=OUT_OF_SCOPE_MESSAGE,
                citations=[],
                evidence_found=False,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
            )

        if scope_status == "no_evidence" or should_abstain(results):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return GenerateResponse(
                query=request.query,
                answer=(
                    f"{NO_EVIDENCE_MESSAGE} "
                    "Please try rephrasing or broadening your clinical query."
                ),
                citations=[],
                evidence_found=False,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
            )

        # 3. Assemble evidence context
        evidence_text = assemble_evidence(filtered_results if filtered_results else results)
        user_prompt = construct_user_prompt(request.query, evidence_text)

        # 4. Synthesize answer using OmniRoute LLM client
        client = LLMClient(settings)
        answer = await client.generate_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # 5. Extract and map citations
        citations = extract_citations(answer, filtered_results if filtered_results else results)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return GenerateResponse(
            query=request.query,
            answer=answer.strip(),
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
