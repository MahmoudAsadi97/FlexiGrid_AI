"""FlexiGrid MCP server.

Exposes the shared tool registry (``tools.py``) over the Model Context
Protocol so any MCP host — the bundled agent via ``mcp_host.py``, an IDE, or
another team's client — can call the same typed functions the product uses.

Run it standalone (stdio transport):

    cd backend && python -m flexigrid.mcp_server
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import tools as toolbox

mcp = FastMCP("FlexiGrid Tools")


@mcp.tool()
def get_grid_snapshot(use_live: bool = False) -> dict:
    """Hourly retail tariff and derived Belgian grid-stress series with
    provenance (live-derived from Elia ods002+ods086, or the labelled frozen
    fixture)."""
    return toolbox.get_grid_snapshot(use_live=use_live)


@mcp.tool()
def retrieve_evidence(query: str, top_k: int = 4,
                      mode: Literal["bm25", "dense", "hybrid"] = "hybrid") -> list[dict]:
    """Ranked retrieval over the household/grid corpus with stable citation
    IDs and per-mode (BM25/dense) scores."""
    return toolbox.retrieve_evidence(query, top_k=top_k, mode=mode)


@mcp.tool()
def extract_constraints(mission: str, use_llm: bool = True) -> dict:
    """Convert a natural-language household mission into typed, sanitized
    task constraints (LLM extraction with a rule-based fallback)."""
    return toolbox.extract_constraints(mission, use_llm=use_llm)


@mcp.tool()
def optimize_schedule(spec: dict | None = None,
                      objective: Literal["balanced", "cost", "grid"] | None = None,
                      use_live: bool = False) -> dict:
    """Deterministic joint constrained search under time windows and the
    connection-capacity cap; returns the schedule, validation, and an
    earliest-start baseline for comparison."""
    return toolbox.optimize_schedule(spec=spec, objective=objective,
                                     use_live=use_live)


@mcp.tool()
def validate_schedule(schedule: list[dict], max_load_kw: float = 4.6,
                      avoid_hours: list[int] | None = None) -> dict:
    """Independent critic: re-check any schedule hour by hour against task
    windows, avoid-hours, and the capacity cap."""
    return toolbox.validate_schedule(schedule, max_load_kw=max_load_kw,
                                     avoid_hours=avoid_hours)


if __name__ == "__main__":
    mcp.run()
