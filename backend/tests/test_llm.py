"""LLM client: JSON extraction, structured output, repair, availability."""

import os
import unittest

from tests import helpers

from flexigrid.llm import LocalLLM, LLMConfig, extract_json, get_llm
from flexigrid.models import AgentDecision, Explanation


class ExtractJsonTests(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_object_with_prose_and_fences(self):
        text = 'Sure! Here you go:\n```json\n{"tool": "finish", "args": {}}\n``` hope it helps'
        self.assertEqual(extract_json(text), {"tool": "finish", "args": {}})

    def test_nested_braces_and_strings(self):
        text = 'prefix {"a": {"b": "}{"}, "c": [1, 2]} suffix'
        self.assertEqual(extract_json(text), {"a": {"b": "}{"}, "c": [1, 2]})

    def test_first_invalid_then_valid_object(self):
        text = '{broken {"valid": true}'
        self.assertEqual(extract_json(text), {"valid": True})

    def test_no_object_returns_none(self):
        self.assertIsNone(extract_json("no json here"))
        self.assertIsNone(extract_json("[1, 2, 3]"))


class StructuredOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_mock_llm()
        cls.llm = get_llm()

    def test_available_and_lists_models(self):
        self.assertTrue(self.llm.available(max_age_seconds=0))
        self.assertIn("mock-planner-1", self.llm.list_models())

    def test_structured_agent_decision(self):
        decision, notes = self.llm.structured(
            AgentDecision,
            "You are the planning agent of FlexiGrid.",
            "Current state:\nconstraints extracted: no\n\nChoose the next tool.")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.tool, "extract_constraints")
        self.assertEqual(notes, [])

    def test_repair_round_trip_on_malformed_json(self):
        os.environ["MOCK_LLM_MALFORMED_EVERY"] = "1"  # first reply truncated
        try:
            decision, notes = self.llm.structured(
                AgentDecision,
                "You are the planning agent of FlexiGrid.",
                "Current state:\nconstraints extracted: no\n\nChoose the next tool.",
                repair_rounds=1)
        finally:
            os.environ.pop("MOCK_LLM_MALFORMED_EVERY", None)
        # The mock truncates only the first attempt (the repair prompt contains
        # 'corrected JSON'), so the repair round must succeed.
        self.assertIsNotNone(decision)
        self.assertTrue(any("invalid" in note for note in notes))

    def test_explanation_schema_roundtrip(self):
        explanation, _ = self.llm.structured(
            Explanation,
            "You explain an already-validated household energy schedule.",
            '{"allowed_citation_ids": ["manual-ev#1"], "verified_plan": '
            '{"total_cost_eur": 1.5, "peak_load_kw": 4.1}}')
        self.assertIsNotNone(explanation)
        self.assertEqual(explanation.citation_ids, ["manual-ev#1"])


class UnavailableEndpointTests(unittest.TestCase):
    def test_unreachable_endpoint_reports_unavailable(self):
        llm = LocalLLM(LLMConfig(base_url="http://127.0.0.1:9/v1",
                                 model="nothing", timeout=2))
        self.assertFalse(llm.available(max_age_seconds=0))
        result, notes = llm.structured(
            AgentDecision, "system", "user", repair_rounds=0)
        self.assertIsNone(result)
        self.assertTrue(any("llm-unavailable" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
