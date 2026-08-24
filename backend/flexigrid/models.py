from __future__ import annotations

from pydantic import BaseModel, Field


class Explanation(BaseModel):
    summary: str = Field(description="A concise explanation of the verified plan")
    rationale: list[str] = Field(min_length=2, max_length=4)
    citation_ids: list[str] = Field(min_length=1)
    limitation: str


class PlanRequest(BaseModel):
    prompt: str
    objective: str = "balanced"
    use_llm: bool = False


class PlanResponse(BaseModel):
    plan: dict
    evidence: list[dict]
    explanation: Explanation
    mode: str
