import json
import unittest
from pathlib import Path

from flexigrid.agent import generate_plan
from flexigrid.core import create_demo_plan, demo_tasks, optimize, validate
from flexigrid.retrieval import retrieve


class PlannerTests(unittest.TestCase):
    def test_all_objectives_are_feasible(self):
        for objective in ("balanced", "cost", "grid"):
            with self.subTest(objective=objective):
                schedule = optimize(demo_tasks(), objective)
                result = validate(schedule)
                self.assertTrue(result["valid"])
                self.assertLessEqual(result["peak_load_kw"], 4.6)

    def test_plan_is_reproducible(self):
        first = create_demo_plan("balanced")
        second = create_demo_plan("balanced")
        self.assertEqual(first, second)

    def test_retrieval_prefers_ev_manual(self):
        results = retrieve("charge the EV in eco mode before morning", top_k=2)
        self.assertEqual(results[0]["chunk_id"], "manual-ev-04")

    def test_retrieval_returns_requested_depth(self):
        self.assertEqual(len(retrieve("Elia wind load forecast", top_k=4)), 4)

    def test_offline_explanation_only_uses_retrieved_citations(self):
        result = generate_plan("charge the EV before morning", use_llm=False)
        retrieved = {item["chunk_id"] for item in result["evidence"]}
        cited = set(result["explanation"].citation_ids)
        self.assertTrue(cited)
        self.assertTrue(cited.issubset(retrieved))

    def test_frozen_elia_fixture_is_explicitly_labelled(self):
        fixture_path = Path(__file__).resolve().parent.parent / "data" / "elia_demo_snapshot.json"
        snapshot = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["mode"], "frozen-demo-fixture")
        self.assertIn("not asserted as a live Elia record", snapshot["warning"])
        self.assertEqual(set(snapshot["dataset_contracts"]), {"ods002", "ods086", "ods201"})


if __name__ == "__main__":
    unittest.main()
