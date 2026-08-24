"""MCP host: run the FlexiGrid agent over a real Model Context Protocol session.

Spawns ``python -m flexigrid.mcp_server`` as a subprocess, opens an MCP
client session over stdio, lists the server's tools, and hands the agent an
executor whose every tool call travels through the protocol. This is the
end-to-end MCP demonstration:

    cd backend && python -m flexigrid.mcp_host "Charge the EV and run the
    dishwasher before 07:00"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .agent import run_agent
from .models import Objective


def _unwrap(result: Any) -> Any:
    """Convert an MCP CallToolResult into plain JSON data."""
    if getattr(result, "isError", False):
        message = ""
        for item in getattr(result, "content", []) or []:
            message += getattr(item, "text", "")
        raise RuntimeError(message or "MCP tool call failed")
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    texts = [getattr(item, "text", "") for item in getattr(result, "content", []) or []]
    joined = "\n".join(text for text in texts if text)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


class McpExecutor:
    """Tool executor backed by a live MCP client session."""

    transport = "mcp-stdio"

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        result = await self._session.call_tool(tool, arguments=args)
        return _unwrap(result)


async def run_agent_over_mcp(mission: str,
                             objective: Objective | None = None,
                             retrieval_mode: str = "hybrid",
                             use_llm: bool = True) -> dict[str, Any]:
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "flexigrid.mcp_server"],
        env=dict(os.environ))  # forward FLEXIGRID_* so server-side LLM calls work
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            executor = McpExecutor(session)
            result = await run_agent(mission, objective=objective,
                                     retrieval_mode=retrieval_mode,
                                     use_llm=use_llm, executor=executor)
            result["modes"]["mcp_tools_listed"] = sorted(
                tool.name for tool in listing.tools)
            return result


def main() -> None:
    mission = " ".join(sys.argv[1:]) or (
        "Charge the EV, run the dishwasher and laundry before 07:00, and "
        "preheat the home by 06:30. Keep load below 4.6 kW.")
    print(f"Mission: {mission}\n")
    result = asyncio.run(run_agent_over_mcp(mission))
    print("Tools advertised by the MCP server:",
          ", ".join(result["modes"]["mcp_tools_listed"]))
    print(f"\nAgent trace ({result['modes']['transport']}):")
    for record in result["trace"]:
        status = "ok " if record["ok"] else "ERR"
        print(f"  [{record['step']}] {status} {record['tool']:<20} "
              f"{record['duration_ms']:>5} ms  {record['summary']} "
              f"({record['decided_by']})")
    plan = result["plan"]
    print(f"\nPlan: €{plan['total_cost_eur']}, peak {plan['peak_load_kw']} kW, "
          f"valid={plan['validation']['valid']}")
    print(f"Explanation ({result['modes']['explanation']}): "
          f"{result['explanation']['summary']}")
    print("Citations:", ", ".join(result['explanation']['citation_ids']))


if __name__ == "__main__":
    main()
