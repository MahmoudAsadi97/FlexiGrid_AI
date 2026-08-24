from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .core import create_demo_plan, demo_tasks, validate, ScheduledTask
from .elia_client import EliaClient
from .retrieval import retrieve

mcp = FastMCP("FlexiGrid Tools")


@mcp.tool()
def get_elia_grid_snapshot(use_live: bool = False) -> dict:
    """Return live Elia records when available, otherwise the reproducible frozen fixture."""
    return EliaClient().snapshot(use_live=use_live)


@mcp.tool()
def retrieve_household_evidence(query: str, top_k: int = 4) -> list[dict]:
    """Retrieve cited manual, comfort, tariff, and Elia dataset chunks."""
    return retrieve(query, top_k=min(max(top_k, 1), 6))


@mcp.tool()
def optimize_household_plan(objective: Literal["balanced", "cost", "grid"] = "balanced") -> dict:
    """Create and machine-validate a schedule under time-window and 4.6 kW constraints."""
    return create_demo_plan(objective)


@mcp.tool()
def get_demo_device_constraints() -> list[dict]:
    """Return typed device constraints used by the demonstration planner."""
    return [asdict(task) for task in demo_tasks()]


if __name__ == "__main__":
    mcp.run()
