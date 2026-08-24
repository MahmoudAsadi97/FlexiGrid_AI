"""FlexiGrid HTTP API.

Serves the dashboard (CORS-enabled for local development) and any other
client. Every planning response carries the full agent trace, the extracted
constraints, retrieval scores, and mode flags, so the interface can show
exactly what ran — no simulated telemetry.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
    version="2.0.0",
    description="Evidence-grounded household energy planning with a local "
                "LLM, hybrid RAG, MCP tools, and a deterministic optimizer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FLEXIGRID_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.post("/api/retrieve")
def retrieve_endpoint(payload: dict) -> list[dict]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    top_k = int(payload.get("top_k", 4))
    mode = str(payload.get("mode", "hybrid"))
    try:
        return get_index().retrieve(query, top_k=top_k, mode=mode)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/intent")
def intent_endpoint(payload: dict) -> dict:
    mission = str(payload.get("prompt", "")).strip()
    if not mission:
        raise HTTPException(status_code=422, detail="prompt is required")
    result = extract_intent(mission, llm=get_llm(),
                            use_llm=bool(payload.get("use_llm", True)))
    return {"spec": result.spec.model_dump(), "mode": result.mode,
            "adjustments": result.adjustments, "notes": result.notes}


@app.post("/api/agent/plan", response_model=AgentResponse)
async def agent_plan(request: PlanRequest) -> dict:
    try:
        result = await run_agent(
            request.prompt,
            objective=request.objective,
            retrieval_mode=request.retrieval_mode,
            use_llm=request.use_llm,
        )
    except InfeasibleMission as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        result["modes"]["retrieval_backend"] = get_index().backend.name
    except Exception:  # pragma: no cover
        pass
    return result


@app.post("/api/plan", response_model=AgentResponse)
async def plan_legacy(request: PlanRequest) -> dict:
    """Backwards-compatible alias for /api/agent/plan."""
    return await agent_plan(request)


@app.get("/api/elia-snapshot")
def elia_snapshot_raw(use_live: bool = False) -> dict:
    """Raw adapter output, useful for the data-pipeline demo."""
    return EliaClient().snapshot(use_live=use_live)
