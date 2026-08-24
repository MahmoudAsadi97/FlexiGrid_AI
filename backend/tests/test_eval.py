"""Evaluation harness: deterministic sections must run and be well-formed."""

import unittest

from tests import helpers

from flexigrid.evaluate import (evaluate_greedy_ablation, evaluate_intent,
                                evaluate_retrieval)


class EvalHarnessTests(unittest.TestCase):
    def test_retrieval_eval_covers_all_modes(self):
        results = evaluate_retrieval()
        for mode in ("bm25", "dense", "hybrid"):
            self.assertIn(mode, results)
            self.assertGreaterEqual(results[mode]["queries"], 30)
            self.assertGreaterEqual(results[mode]["recall_at_4"], 0.0)
            self.assertLessEqual(results[mode]["recall_at_4"], 1.0)

    def test_bm25_baseline_meets_quality_bar(self):
        results = evaluate_retrieval()
        self.assertGreaterEqual(results["bm25"]["recall_at_4"], 0.9)
        self.assertGreaterEqual(results["bm25"]["hit_at_1"], 0.8)

    def test_intent_eval_rules_mode(self):
        helpers.use_no_llm()
        from flexigrid.llm import get_llm
        results = evaluate_intent(get_llm(), use_llm=False)
        self.assertIn("rules", results)
        self.assertNotIn("llm", results)
        self.assertGreaterEqual(results["rules"]["exact_match"], 0.6)
        self.assertEqual(results["rules"]["failures"], [])

    def test_greedy_ablation_demonstrates_failure_class(self):
        results = evaluate_greedy_ablation()
        self.assertGreaterEqual(results["greedy_failures"], 1)
        self.assertEqual(results["joint_failures"], 0)
        tight = [row for row in results["cases"]
                 if row["case"].startswith("tight-window")]
        self.assertTrue(tight)
        self.assertTrue(all(not row["greedy_valid"] for row in tight))
        self.assertTrue(all(row["joint_cost_eur"] is not None
                            for row in results["cases"]))


if __name__ == "__main__":
    unittest.main()
