"""Model Context Protocol: real stdio round-trip against the FastMCP server."""

import sys
import unittest

from tests import helpers

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from flexigrid.mcp_host import _unwrap, run_agent_over_mcp

EXPECTED_TOOLS = {"get_grid_snapshot", "retrieve_evidence",
                  "extract_constraints", "optimize_schedule",
                  "validate_schedule"}


class McpStdioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        helpers.use_no_llm()

    async def test_server_lists_all_tools_and_answers_calls(self):
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "flexigrid.mcp_server"])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                self.assertEqual(names, EXPECTED_TOOLS)

                retrieval = _unwrap(await session.call_tool(
                    "retrieve_evidence",
                    arguments={"query": "EV eco mode", "top_k": 2}))
                self.assertEqual(len(retrieval), 2)
                self.assertEqual(retrieval[0]["doc_id"], "manual-ev")

                snapshot = _unwrap(await session.call_tool(
                    "get_grid_snapshot", arguments={"use_live": False}))
                self.assertEqual(snapshot["mode"], "frozen-demo-fixture")

    async def test_full_agent_over_mcp_transport(self):
        result = await run_agent_over_mcp(
            "Charge the EV and run the laundry before 07:00", use_llm=False)
        self.assertEqual(result["modes"]["transport"], "mcp-stdio")
        self.assertEqual(set(result["modes"]["mcp_tools_listed"]),
                         EXPECTED_TOOLS)
        self.assertTrue(result["plan"]["validation"]["valid"])
        self.assertTrue(all(record["transport"] == "mcp-stdio"
                            for record in result["trace"]
                            if record["tool"] != "finish"))


if __name__ == "__main__":
    unittest.main()
