"""FlexiGrid HTTP API.

Serves the dashboard (CORS-enabled for local development) and any other
client. Every planning response carries the full agent trace, the extracted
constraints, retrieval scores, and mode flags, so the interface can show
exactly what ran — no simulated telemetry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from typing import Literal
from .planning import PlanningProblem, PlanningError, NoIncumbentError, solve, validate_starts
from .uncertainty import CalibrationRequest, calibrate_reserve

from .agent import run_agent
from .core import InfeasibleMission
from .elia_client import EliaClient
from .intent import extract_intent
from .llm import get_llm
from .models import AgentResponse, PlanRequest
from .retrieval import get_index
from .tools import get_grid_snapshot

app = FastAPI(
    title="FlexiGrid AI API",
    version="3.0.0",
    description="Evidence-grounded household energy planning with a local "
                "LLM, hybrid RAG, MCP tools, and a deterministic optimizer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FLEXIGRID_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-process admission control, not authentication or a distributed quota.
_PLANNING_SLOT = BoundedSemaphore(1)

SCENARIOS = [
    {
        "id": "morning",
        "label": "Ready by morning",
        "shortLabel": "Morning",
        "objective": "balanced",
        "prompt": "Charge the EV, run laundry and dishwasher before 07:00. "
                  "Preheat the home to 20.5 °C by 06:30. Keep controllable "
                  "load below 4.6 kW.",
    },
    {
        "id": "grid-friendly",
        "label": "Support the grid",
        "shortLabel": "Grid friendly",
        "objective": "grid",
        "prompt": "Finish the EV charge, laundry and dishwasher between 08:00 "
                  "and 16:00 and support the grid: prefer low-load, high-wind "
                  "hours. Keep controllable load below 4.6 kW.",
    },
    {
        "id": "peak-avoidance",
        "label": "Avoid evening peak",
        "shortLabel": "Peak shield",
        "objective": "cost",
        "prompt": "Charge the EV and run the dishwasher after 14:00 but "
                  "before 23:00 at the lowest cost, and avoid the 17:00 to "
                  "20:00 evening peak. Keep controllable load below 4.6 kW.",
    },
]


@app.get("/health")
def health() -> dict:
    llm = get_llm()
    llm_live = llm.available()
    index = get_index()
    backend_name = None
    backend_model = None
    try:
        backend_name = index.backend.name
        backend_model = index.backend.model
    except Exception:  # pragma: no cover - embeddings never block health
        pass
    return {
        "status": "ok",
        "llm": {
            "live": llm_live,
            "base_url": llm.config.base_url,
            "model": llm.config.model if llm_live else None,
            "last_error": None if llm_live else llm.last_error,
        },
        "embeddings": {"backend": backend_name, "model": backend_model},
        "corpus": {"chunks": len(index.chunks), "fingerprint": index.fingerprint},
        "elia_live": os.getenv("ELIA_USE_LIVE", "false").lower() == "true",
    }


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return SCENARIOS


@app.get("/api/grid-snapshot")
def grid_snapshot(use_live: bool | None = None) -> dict:
    return get_grid_snapshot(use_live=use_live)


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=8)
    mode: Literal["bm25", "dense", "hybrid"] = "hybrid"


class IntentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    use_llm: StrictBool = True


@app.post("/api/retrieve")
def retrieve_endpoint(payload: RetrievalRequest) -> list[dict]:
    if not payload.query.strip():
        raise HTTPException(status_code=422, detail="query is required")
    return get_index().retrieve(payload.query, top_k=payload.top_k, mode=payload.mode)


@app.post("/api/intent")
def intent_endpoint(payload: IntentRequest) -> dict:
    if not payload.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt is required")
    try:
        result = extract_intent(payload.prompt, llm=get_llm(), use_llm=payload.use_llm)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"spec": result.spec.model_dump(), "mode": result.mode,
            "adjustments": result.adjustments, "notes": result.notes}


@app.post("/api/planning/solve")
def solve_advanced(problem: PlanningProblem) -> dict:
    """15/30/60-minute scheduling with power profiles and whole-home headroom."""
    if not _PLANNING_SLOT.acquire(blocking=False):
        raise HTTPException(429, "Another numerical solve is running", headers={"Retry-After": "1"})
    try:
        return solve(problem)
    except PlanningError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except NoIncumbentError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        _PLANNING_SLOT.release()


class ScheduleAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem: PlanningProblem
    starts: dict[str, StrictInt] = Field(max_length=64)


@app.post("/api/planning/validate")
def audit_advanced(request: ScheduleAuditRequest) -> dict:
    """Audit external start assignments against the supplied original problem."""
    return validate_starts(request.problem, request.starts)


@app.post("/api/planning/calibrate")
def calibrate_advanced(request: CalibrationRequest) -> dict:
    """Reserve from held-out forecasts, not a trained forecasting model."""
    try:
        return calibrate_reserve(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/agent/plan", response_model=AgentResponse)
async def agent_plan(request: PlanRequest) -> dict:
    try:
        result = await run_agent(
            request.prompt,
            objective=request.objective,
            retrieval_mode=request.retrieval_mode,
            use_llm=request.use_llm,
        )
    except (InfeasibleMission, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except NoIncumbentError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    try:
        result["modes"]["retrieval_backend"] = get_index().backend.name
    except Exception:  # pragma: no cover
        pass
    return result


@app.post("/api/plan", response_model=AgentResponse)
async def plan_legacy(request: PlanRequest) -> dict:
    """Backwards-compatible alias for /api/agent/plan."""
    return await agent_plan(request)


@app.get("/api/evaluation")
def evaluation_results() -> dict:
    """The measured evaluation (results.json) for the dashboard's numbers.

    Regenerate with ``python -m flexigrid.evaluate``; the file records which
    model and embedding backend produced every figure.
    """
    path = Path(__file__).resolve().parent.parent / "evaluation" / "results.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="results.json not generated yet — run "
                   "python -m flexigrid.evaluate")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/elia-snapshot")
def elia_snapshot_raw(use_live: bool = False) -> dict:
    """Raw adapter output, useful for the data-pipeline demo."""
    return EliaClient().snapshot(use_live=use_live)
