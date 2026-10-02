"""Pydantic models shared by the intent extractor, agent, API, and tests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Objective = Literal["balanced", "cost", "grid"]

KNOWN_DEVICES: dict[str, dict[str, object]] = {
    "ev": {"name": "EV charge · eco mode", "power_kw": 3.6, "duration_hours": 2,
           "source_id": "manual-ev#1", "power_range": (1.4, 7.4)},
    "dishwasher": {"name": "Dishwasher · Eco 50 °C", "power_kw": 0.5, "duration_hours": 2,
                   "source_id": "manual-dishwasher#0", "power_range": (0.3, 1.8)},
    "laundry": {"name": "Washing machine · 40 °C", "power_kw": 0.8, "duration_hours": 1,
                "source_id": "manual-washer#0", "power_range": (0.4, 2.0)},
    "heat": {"name": "Heat-pump preheat", "power_kw": 1.4, "duration_hours": 2,
             "source_id": "manual-heatpump#0", "power_range": (0.6, 2.2)},
}

DEFAULT_MAX_LOAD_KW = 4.6


class TaskSpec(BaseModel):
    """One flexible task extracted from a mission."""
    task_id: Literal["ev", "dishwasher", "laundry", "heat"]
    power_kw: float = Field(gt=0, le=8)
    duration_hours: int = Field(ge=1, le=6)
    earliest_start: int = Field(ge=0, le=23)
    latest_end: int = Field(ge=1, le=24)


class MissionSpec(BaseModel):
    """Typed constraints extracted from a natural-language mission."""
    tasks: list[TaskSpec] = Field(min_length=1, max_length=4)
    objective: Objective = "balanced"
    max_load_kw: float = Field(default=DEFAULT_MAX_LOAD_KW, gt=1, le=9.2)
    avoid_hours: list[int] = Field(default_factory=list, max_length=24)
    notes: str = ""


class Explanation(BaseModel):
    summary: str = Field(description="Concise explanation of the verified plan")
    rationale: list[str] = Field(min_length=2, max_length=4)
    citation_ids: list[str] = Field(min_length=0, max_length=6)
    limitation: str


class AgentDecision(BaseModel):
    """One step of the tool-using agent loop."""
    thought: str = Field(max_length=500)
    tool: Literal["get_grid_snapshot", "retrieve_evidence", "extract_constraints",
                  "optimize_schedule", "validate_schedule", "finish"]
    args: dict = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    step: int
    tool: str
    args: dict
    ok: bool
    duration_ms: int
    summary: str
    transport: str = "direct"
    decided_by: Literal["llm", "guardrail"] = "llm"
    thought: str = ""


class PlanRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    objective: Objective | None = None
    retrieval_mode: Literal["bm25", "dense", "hybrid"] = "hybrid"
    use_llm: bool = True


class AgentResponse(BaseModel):
    plan: dict
    spec: dict
    evidence: list[dict]
    explanation: Explanation
    trace: list[ToolCallRecord]
    modes: dict
