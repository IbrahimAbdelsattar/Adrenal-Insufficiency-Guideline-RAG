"""Generation endpoint — DEFINED BUT NOT IMPLEMENTED (FR-034).

Constitution Principle V forbids generation work until retrieval demonstrably returns
reasonable evidence. This 501 is the correct Day 1 behaviour, not an unfinished task;
quickstart V9 asserts it.

The contract this will satisfy lives in contracts/generation-api.yaml. Any future
implementation is bound by Principle I: when no evidence clears the relevance floor,
it must abstain rather than answer from model memory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["generation"])


class GenerateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=0, ge=0, le=50)


@router.post("/generate", status_code=501)
def generate_answer(request: GenerateRequest) -> dict:
    raise HTTPException(
        status_code=501,
        detail=(
            "Generation is not implemented. Day 1 scope is ingestion and retrieval "
            "only (Constitution Principle V). Use POST /api/search."
        ),
    )
