"""FastAPI surface: health, retrieval, intent, agent plan, error handling."""

import unittest

from fastapi.testclient import TestClient

from tests import helpers

from flexigrid.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_no_llm()  # API must be fully functional without a model
        cls.client = TestClient(app)

    def test_health_reports_components(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["llm"]["live"])
        self.assertIn(body["embeddings"]["backend"], ("tfidf", "ollama", "sbert"))
        self.assertGreaterEqual(body["corpus"]["chunks"], 40)

    def test_scenarios_listing(self):
        response = self.client.get("/api/scenarios")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)

    def test_grid_snapshot_frozen(self):
        response = self.client.get("/api/grid-snapshot")
        body = response.json()
        self.assertEqual(body["mode"], "frozen-demo-fixture")
        self.assertEqual(len(body["normalized_hourly"]["tariff_eur_per_kwh"]), 24)

    def test_retrieve_endpoint(self):
        response = self.client.post("/api/retrieve",
                                    json={"query": "EV eco mode", "top_k": 3})
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["doc_id"], "manual-ev")

    def test_retrieve_requires_query(self):
        self.assertEqual(
            self.client.post("/api/retrieve", json={}).status_code, 422)

    def test_intent_endpoint(self):
        response = self.client.post(
            "/api/intent", json={"prompt": "Charge the EV before 07:00"})
        body = response.json()
        self.assertEqual(body["mode"], "rules")
        self.assertEqual(body["spec"]["tasks"][0]["task_id"], "ev")

    def test_agent_plan_end_to_end(self):
        response = self.client.post("/api/agent/plan", json={
            "prompt": "Charge the EV and run the dishwasher before 07:00",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["plan"]["validation"]["valid"])
        self.assertTrue(body["trace"])
        self.assertTrue(body["evidence"])
        self.assertLessEqual(body["plan"]["peak_load_kw"], 4.6)
        self.assertIn("baseline", body["plan"])
        self.assertIsNotNone(body["modes"]["retrieval_backend"])

    def test_agent_plan_respects_objective_override(self):
        response = self.client.post("/api/agent/plan", json={
            "prompt": "Charge the EV before 07:00", "objective": "cost"})
        self.assertEqual(response.json()["plan"]["objective"], "cost")

    def test_infeasible_mission_returns_422(self):
        response = self.client.post("/api/agent/plan", json={
            "prompt": "Charge the EV before 01:00, keep load below 2.0 kW"})
        self.assertEqual(response.status_code, 422)

    def test_legacy_plan_alias(self):
        response = self.client.post("/api/plan", json={
            "prompt": "Run the laundry before 09:00"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["plan"]["validation"]["valid"])


class ApiWithLlmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.use_mock_llm()
        cls.client = TestClient(app)

    def test_health_shows_live_model(self):
        body = self.client.get("/health").json()
        self.assertTrue(body["llm"]["live"])
        self.assertEqual(body["llm"]["model"], "mock-planner-1")

    def test_agent_plan_uses_llm_modes(self):
        response = self.client.post("/api/agent/plan", json={
            "prompt": "Charge the EV and preheat the home before 07:00"})
        body = response.json()
        self.assertTrue(body["modes"]["llm_live"])
        self.assertEqual(body["modes"]["intent"], "llm")


if __name__ == "__main__":
    unittest.main()
