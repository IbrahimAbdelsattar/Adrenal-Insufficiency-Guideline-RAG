"""Generation endpoint for answering clinical queries via RAG."""

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate")
async def generate_answer(request: GenerateRequest) -> GenerateResponse:
    """Generate an answer grounded in retrieved clinical guidelines.
    
    If no relevant evidence is found, the model will abstain.
    """
    settings = get_settings()
    started = time.perf_counter()
    
    try:
        # 1. Retrieve evidence
        retriever = get_retriever(settings)
        top_k = request.top_k or settings.top_k
        results = retriever.search(request.query, top_k)
        
        # 2. Check abstention
        if should_abstain(results):
            # Abstain from LLM call
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return GenerateResponse(
                query=request.query,
                answer=(
                    "I am sorry, but I could not find enough relevant information in the "
                    "clinical guidelines to confidently answer your question. "
                    "Please try rephrasing or broadening your search."
                ),
                citations=[],
                evidence_found=False,
                disclaimer=DISCLAIMER,
                model=settings.generation_model,
                latency_ms=elapsed_ms,
            )
            
        # 3. Assemble context
        evidence_text = assemble_evidence(results)
        user_prompt = construct_user_prompt(request.query, evidence_text)
        
        # 4. Generate Answer
        client = LLMClient(settings)
        answer = await client.generate_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        
        # 5. Extract citations
        citations = extract_citations(answer, results)
        
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
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Generation failed: %s", exc)
        raise HTTPException(
            status_code=503, 
            detail="LLM Answer Generation is currently in staged validation mode. Please review the retrieved guideline evidence cards below."
        )
