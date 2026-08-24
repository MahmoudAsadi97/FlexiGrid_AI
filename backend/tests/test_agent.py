"""Agent loop: deterministic path, LLM path, guardrails, citation guard."""

import os
import unittest

from tests import helpers

from flexigrid.agent import run_agent
from flexigrid.core import InfeasibleMission

MISSION = ("Charge the EV and run the dishwasher before 07:00. "
           "Keep controllable load below 4.6 kW.")


class DeterministicAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        helpers.use_no_llm()

    async def test_pipeline_completes_without_llm(self):
        result = await run_agent(MISSION, use_llm=False)
        self.assertTrue(result["plan"]["validation"]["valid"])
        self.assertFalse(result["modes"]["llm_live"])
        self.assertEqual(result["modes"]["intent"], "rules")
        self.assertEqual(result["modes"]["explanation"], "deterministic")
        tools_run = [record["tool"] for record in result["trace"]]
        for tool in ("extract_constraints", "get_grid_snapshot",
                     "retrieve_evidence", "optimize_schedule",
                     "validate_schedule"):
            self.assertIn(tool, tools_run)
        self.assertTrue(all(record["decided_by"] == "guardrail"
                            for record in result["trace"]))

    async def test_mission_actually_drives_the_plan(self):
        ev_only = await run_agent("Charge the EV before 07:00", use_llm=False)
        many = await run_agent(MISSION, use_llm=False)
        self.assertEqual([t["task_id"] for t in ev_only["spec"]["tasks"]], ["ev"])
        self.assertEqual(len(many["spec"]["tasks"]), 2)
        self.assertNotEqual(ev_only["plan"]["total_cost_eur"],
                            many["plan"]["total_cost_eur"])

    async def test_deadline_change_changes_schedule_window(self):
        early = await run_agent("Charge the EV before 05:00", use_llm=False)
        late = await run_agent("Charge the EV after 14:00 before 23:00",
                               use_llm=False)
        early_end = max(t["end"] for t in early["plan"]["schedule"])
        late_start = min(t["start"] for t in late["plan"]["schedule"])
        self.assertLessEqual(early_end, 5)
        self.assertGreaterEqual(late_start, 14)

    async def test_infeasible_mission_raises(self):
        with self.assertRaises(InfeasibleMission):
            # 2h EV charge that must finish by 01:00 with 1 kW cap
            await run_agent("Charge the EV before 01:00, keep load below "
                            "2.0 kW", use_llm=False)

    async def test_citations_subset_of_retrieved(self):
        result = await run_agent(MISSION, use_llm=False)
        retrieved = {chunk["chunk_id"] for chunk in result["evidence"]}
        cited = set(result["explanation"]["citation_ids"])
        self.assertTrue(cited)
        self.assertTrue(cited.issubset(retrieved))

    async def test_deterministic_replay(self):
        first = await run_agent(MISSION, use_llm=False)
        second = await run_agent(MISSION, use_llm=False)
        self.assertEqual(first["plan"], second["plan"])
        self.assertEqual(first["spec"], second["spec"])


class LlmAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        helpers.use_mock_llm()
        os.environ.pop("MOCK_LLM_ROGUE", None)

    async def test_llm_drives_the_loop(self):
        result = await run_agent(MISSION)
        self.assertTrue(result["modes"]["llm_live"])
        self.assertTrue(result["plan"]["validation"]["valid"])
        llm_steps = [record for record in result["trace"]
                     if record["decided_by"] == "llm"]
        self.assertGreaterEqual(len(llm_steps), 4)
        self.assertEqual(result["modes"]["intent"], "llm")
        self.assertEqual(result["modes"]["explanation"], "llm")

    async def test_trace_records_thoughts_and_timings(self):
        result = await run_agent(MISSION)
        for record in result["trace"]:
            self.assertGreaterEqual(record["duration_ms"], 0)
            if record["decided_by"] == "llm":
                self.assertTrue(record["thought"])

    async def test_rogue_model_is_stopped_by_guardrails(self):
        os.environ["MOCK_LLM_ROGUE"] = "1"
        try:
            result = await run_agent(MISSION)
        finally:
            os.environ.pop("MOCK_LLM_ROGUE", None)
        # rogue mode tries to finish before planning; guardrails must both
        # overrule the premature finish and complete the pipeline.
        self.assertTrue(result["plan"]["validation"]["valid"])
        self.assertTrue(any("overruled" in note
                            for note in result["modes"]["decision_notes"]))
        self.assertTrue(any(record["decided_by"] == "guardrail"
                            for record in result["trace"]))

    async def test_explanation_cites_only_retrieved_ids(self):
        result = await run_agent(MISSION)
        retrieved = {chunk["chunk_id"] for chunk in result["evidence"]}
        self.assertTrue(set(result["explanation"]["citation_ids"])
                        .issubset(retrieved))


if __name__ == "__main__":
    unittest.main()
