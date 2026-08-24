"""The FlexiGrid tool registry.

One registry backs every consumer: the MCP server exposes these functions to
any MCP host, the in-process agent calls them directly, and the FastAPI layer
reuses them for individual endpoints. Contracts are documented in
``corpus/mcp-contract.md`` — which is itself retrievable, so the model can
read the contracts of its own tools.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from . import core
from .elia_client import EliaClient
from .intent import extract_intent, spec_to_tasks
from .llm import get_llm
from .models import MissionSpec
from .retrieval import retrieve


def _use_live_default() -> bool:
    return os.getenv("ELIA_USE_LIVE", "false").lower() == "true"


def get_grid_snapshot(use_live: bool | None = None) -> dict[str, Any]:
    """Hourly retail tariff + derived grid-stress series with provenance."""
    live = _use_live_default() if use_live is None else bool(use_live)
    return EliaClient().snapshot(use_live=live)


def retrieve_evidence(query: str, top_k: int = 4, mode: str = "hybrid") -> list[dict]:
    """Ranked corpus retrieval with stable citation IDs and per-mode scores."""
    return retrieve(query, top_k=min(max(int(top_k), 1), 8), mode=mode)


def extract_constraints(mission: str, use_llm: bool = True) -> dict[str, Any]:
    """Mission text → typed constraints (LLM when reachable, rules otherwise)."""
    result = extract_intent(mission, llm=get_llm(), use_llm=use_llm)
    return {
        "spec": result.spec.model_dump(),
        "mode": result.mode,
        "adjustments": result.adjustments,
        "notes": result.notes,
    }


def optimize_schedule(spec: dict[str, Any] | None = None,
                      objective: str | None = None,
                      use_live: bool | None = None) -> dict[str, Any]:
    """Joint constrained search over the supplied spec (demo tasks if omitted)."""
    live = _use_live_default() if use_live is None else bool(use_live)
    tariff, stress, snapshot_mode = EliaClient().series(use_live=live)
    if spec:
        mission_spec = MissionSpec.model_validate(spec)
        tasks = spec_to_tasks(mission_spec)
        chosen_objective = objective or mission_spec.objective
        max_load = mission_spec.max_load_kw
        avoid = mission_spec.avoid_hours
    else:
        tasks = core.demo_tasks()
        chosen_objective = objective or "balanced"
        max_load = 4.6
        avoid = []
    if chosen_objective not in ("balanced", "cost", "grid"):
        chosen_objective = "balanced"
    schedule = core.optimize(tasks, chosen_objective,  # type: ignore[arg-type]
                             max_load_kw=max_load, tariff=tariff, stress=stress,
                             avoid_hours=avoid)
    plan = core.plan_to_dict(schedule, chosen_objective,  # type: ignore[arg-type]
                             max_load_kw=max_load, avoid_hours=avoid)
    # The earliest-start baseline is a comparison, never a gate: on tightly
    # pinned missions the naive baseline can be infeasible while the joint
    # search still finds a valid schedule — report that instead of failing.
    try:
        baseline = core.earliest_start_schedule(tasks, max_load_kw=max_load,
                                                tariff=tariff, stress=stress)
        plan["baseline"] = core.plan_to_dict(
            baseline, chosen_objective,  # type: ignore[arg-type]
            max_load_kw=max_load, avoid_hours=avoid)
    except core.InfeasibleMission as error:
        plan["baseline"] = None
        plan["baseline_note"] = (
            f"The naive earliest-start baseline cannot satisfy this mission "
            f"({error}); only the joint constrained search finds a valid "
            f"schedule.")
    plan["snapshot_mode"] = snapshot_mode
    plan["tariff"] = tariff
    plan["stress"] = stress
    return plan


def validate_schedule(schedule: list[dict[str, Any]],
                      max_load_kw: float = 4.6,
                      avoid_hours: list[int] | None = None) -> dict[str, Any]:
    """Independent critic: re-check any schedule against windows and the cap."""
    if not schedule:
        raise ValueError("Nothing to validate: run optimize_schedule first")
    tasks = [core.ScheduledTask(**item) for item in schedule]
    return core.validate(tasks, max_load_kw=max_load_kw,
                         avoid_hours=avoid_hours or [])


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_grid_snapshot": get_grid_snapshot,
    "retrieve_evidence": retrieve_evidence,
    "extract_constraints": extract_constraints,
    "optimize_schedule": optimize_schedule,
    "validate_schedule": validate_schedule,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_grid_snapshot": "Get the hourly retail tariff and derived Belgian grid-stress "
                         "series with provenance (frozen fixture or live-derived).",
    "retrieve_evidence": "Retrieve ranked evidence chunks from the household/grid corpus. "
                         "Args: query (str), top_k (int, default 4), mode "
                         "(bm25|dense|hybrid).",
    "extract_constraints": "Convert the mission text into typed task constraints. "
                           "Args: mission (str).",
    "optimize_schedule": "Run the deterministic joint constrained search. "
                         "Args: spec (object from extract_constraints.spec), "
                         "objective (balanced|cost|grid, optional).",
    "validate_schedule": "Independently re-validate a schedule. Args: schedule "
                         "(list of scheduled tasks), max_load_kw (float).",
}
