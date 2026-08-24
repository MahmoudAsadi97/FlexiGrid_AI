from __future__ import annotations

import os

from fastapi import FastAPI

from .agent import generate_plan
from .elia_client import EliaClient
from .models import PlanRequest, PlanResponse

app = FastAPI(title="FlexiGrid AI API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/grid-snapshot")
def grid_snapshot() -> dict:
    use_live = os.getenv("ELIA_USE_LIVE", "false").lower() == "true"
    return EliaClient().snapshot(use_live=use_live)


@app.post("/api/plan", response_model=PlanResponse)
def plan(request: PlanRequest) -> dict:
    objective = request.objective if request.objective in {"balanced", "cost", "grid"} else "balanced"
    return generate_plan(request.prompt, objective=objective, use_llm=request.use_llm)
