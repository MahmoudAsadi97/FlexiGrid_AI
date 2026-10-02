"""Optimization equivalence, threat-boundary and uncertainty regressions."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError
from fastapi.testclient import TestClient

from tests import helpers
from flexigrid.benchmark_planning import reference_objective, small_problem
from flexigrid import core
from flexigrid.agent import AgentState, DirectExecutor, _decide, _safe_args, run_agent
from flexigrid.api import app
from flexigrid.models import AgentDecision
from flexigrid.planning import (Job, PlanningProblem, PlanningError,
                                NoIncumbentError, solve, validate_starts)
from flexigrid.uncertainty import CalibrationRequest, calibrate_reserve


def problem(**changes):
    data = dict(jobs=[dict(task_id="ev", power_kw=[3.6, 3.6],
                          earliest_start=0, latest_end=4)],
                slot_minutes=15, tariff_eur_per_kwh=[.3, .1, .1, .4],
                stress=[50.] * 4, max_load_kw=4.6, objective="cost")
    return PlanningProblem.model_validate({**data, **changes})


class PlanningTests(unittest.TestCase):
    def test_independent_reference_including_infeasibility(self):
        rng = np.random.default_rng(71)
        for case in range(40):
            p = small_problem(rng, case)
            reference = reference_objective(p)
            if reference is None:
                with self.assertRaises(PlanningError):
                    solve(p)
            else:
                self.assertAlmostEqual(solve(p)["validation"]["objective_value"], reference, places=7)

    def test_reject_boolean_numerical_inputs(self):
        with self.assertRaises(ValidationError):
            problem(max_load_kw=True)

    def test_reject_wrong_length_solver_output(self):
        with patch("flexigrid.planning.milp", return_value=SimpleNamespace(status=0, x=np.array([1.]))):
            with self.assertRaises(NoIncumbentError):
                solve(problem())

    def test_quarter_hour_units(self):
        result = solve(problem())
        self.assertEqual(result["starts"], {"ev": 1})
        self.assertAlmostEqual(result["validation"]["flexible_energy_kwh"], 1.8)
        self.assertAlmostEqual(result["validation"]["flexible_cost_eur"], .18)

    def test_power_weighted_counterexample(self):
        tasks = [core.Task("small", "Small", .5, 1, 0, 2, "manual"),
                 core.Task("large", "Large", 3.6, 1, 0, 3, "manual")]
        schedule = core.optimize(tasks, "cost", 3.6,
                                 [.1, .2, .9] + [1.] * 21, [50.] * 24)
        self.assertEqual({t.task_id: t.start for t in schedule}, {"small": 1, "large": 0})
        self.assertAlmostEqual(sum(t.cost_eur for t in schedule), .46)

    def test_negative_and_zero_prices(self):
        for prices in ([0.] * 4, [-.3, -.1, -.1, -.4], [-.3, 0, .5, -.4]):
            p = problem(tariff_eur_per_kwh=prices)
            self.assertAlmostEqual(solve(p)["validation"]["objective_value"],
                                   solve(p, backend="exact")["validation"]["objective_value"])

    def test_randomized_equivalence_to_exhaustive_oracle(self):
        rng = np.random.default_rng(20261002)
        for case in range(60):
            jobs = [dict(task_id=str(j), power_kw=rng.uniform(.2, 2, size=2).tolist(),
                         earliest_start=0, latest_end=5) for j in range(3)]
            p = problem(jobs=jobs, tariff_eur_per_kwh=rng.uniform(-.2, .6, 5).tolist(),
                        stress=rng.uniform(0, 100, 5).tolist(), max_load_kw=4.5,
                        background_kw=rng.uniform(0, .5, 5).tolist(),
                        objective=("cost", "grid", "balanced")[case % 3])
            with self.subTest(case=case):
                exact, mip = solve(p, backend="exact"), solve(p)
                self.assertTrue(mip["validation"]["valid"])
                self.assertAlmostEqual(exact["validation"]["objective_value"],
                                       mip["validation"]["objective_value"], places=7)

    def test_background_and_reserve_change_schedule(self):
        p = problem(background_kw=[0, 1, 1, 0], reserve_kw=[.2] * 4)
        with self.assertRaises(PlanningError):
            solve(p)
        p = problem(jobs=[dict(task_id="ev", power_kw=[3.6], earliest_start=0, latest_end=4)],
                    background_kw=[0, 1, 1, 0], reserve_kw=[.2] * 4)
        self.assertEqual(solve(p)["starts"], {"ev": 0})

    def test_hard_avoid_never_relaxes(self):
        with self.assertRaises(PlanningError):
            solve(problem(avoid_slots=[0, 1, 2, 3]))

    def test_committed_start_is_preserved(self):
        self.assertEqual(solve(problem(fixed_starts={"ev": 0}))["starts"], {"ev": 0})

    def test_reject_invalid_problem(self):
        cases = [dict(stress=[1.]), dict(tariff_eur_per_kwh=[float("nan")] * 4),
                 dict(avoid_slots=[-1]), dict(avoid_slots=[4]), dict(max_load_kw=0),
                 dict(fixed_starts={"missing": 1}), dict(fixed_starts={"ev": 3}),
                 dict(background_kw=[0.]), dict(reserve_kw=[-1.] * 4)]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                problem(**change)

    def test_duplicate_id_rejected(self):
        j = dict(task_id="same", power_kw=[1.], earliest_start=0, latest_end=4)
        with self.assertRaises(ValidationError):
            problem(jobs=[j, j])

    def test_certificate_checks_id_and_start(self):
        for starts in ({}, {"ev": -1}, {"ev": True}, {"ev": 1, "extra": 0}):
            self.assertFalse(validate_starts(problem(), starts)["valid"])

    def test_solver_limit_not_claimed_infeasible(self):
        fake = SimpleNamespace(status=1, x=None)
        with patch("flexigrid.planning.milp", return_value=fake):
            with self.assertRaises(NoIncumbentError):
                solve(problem())

    def test_feasible_time_limit_reported_honestly(self):
        fake = SimpleNamespace(status=1, x=np.array([0., 1., 0.]), mip_gap=.2,
                               mip_dual_bound=.1)
        with patch("flexigrid.planning.milp", return_value=fake):
            result = solve(problem())
        self.assertEqual(result["solver"]["status"], "feasible-time-limit")
        self.assertEqual(result["solver"]["mip_gap"], .2)

    def test_fractional_solver_output_rejected(self):
        fake = SimpleNamespace(status=1, x=np.array([.5, .5, 0.]))
        with patch("flexigrid.planning.milp", return_value=fake):
            with self.assertRaises(NoIncumbentError):
                solve(problem())

    def test_exact_search_budget(self):
        with self.assertRaises(ValueError):
            solve(problem(), backend="exact", max_exact_combinations=1)

    def test_multiple_infeasible_instances_agree(self):
        for cap in (.1, 1., 3.):
            for backend in ("milp", "exact"):
                with self.subTest(cap=cap, backend=backend), self.assertRaises(PlanningError):
                    solve(problem(max_load_kw=cap), backend=backend)

    def test_replay_and_provenance(self):
        self.assertEqual(solve(problem()), solve(problem()))
        self.assertNotEqual(solve(problem())["problem_sha256"],
                            solve(problem(fixed_starts={"ev": 0}))["problem_sha256"])


class CriticTests(unittest.TestCase):
    def setUp(self):
        self.tasks = core.demo_tasks()
        self.schedule = core.optimize(self.tasks, "cost")

    def test_altered_task_metadata_is_rejected(self):
        for change in (dict(power_kw=.01), dict(duration_hours=1),
                       dict(start=-1, end=1), dict(start=24, end=26),
                       dict(power_kw=float("nan")), dict(power_kw=-1),
                       dict(earliest_start=0, latest_end=24)):
            altered = [replace(self.schedule[0], **change)] + self.schedule[1:]
            with self.subTest(change=change):
                self.assertFalse(core.validate(altered, expected_tasks=self.tasks)["valid"])

    def test_missing_duplicate_and_empty_rejected(self):
        for schedule in ([], self.schedule[:-1], self.schedule + [self.schedule[0]]):
            self.assertFalse(core.validate(schedule, expected_tasks=self.tasks)["valid"])


class UncertaintyTests(unittest.TestCase):
    def test_block_max_and_finite_sample_rank(self):
        request = CalibrationRequest(forecasts_kw=[[1, 1]] * 9,
                                     actuals_kw=[[1 + i / 10, 1] for i in range(9)], alpha=.1)
        result = calibrate_reserve(request)
        self.assertEqual(result["quantile_rank"], 9)
        self.assertAlmostEqual(result["reserve_kw"][0], .8)
        self.assertIn("exchangeable", result["coverage_scope"])

    def test_insufficient_calibration_not_silently_clipped(self):
        with self.assertRaises(ValueError):
            calibrate_reserve(CalibrationRequest(forecasts_kw=[[1]] * 3,
                                                 actuals_kw=[[2]] * 3, alpha=.1))

    def test_ragged_misaligned_and_negative_rejected(self):
        for forecasts, actuals in (([[1], [1, 2]], [[1], [1]]),
                                  ([[1]] * 9, [[1, 2]] * 9),
                                  ([[-1]] * 9, [[1]] * 9)):
            with self.assertRaises(ValueError):
                calibrate_reserve(CalibrationRequest(forecasts_kw=forecasts, actuals_kw=actuals))


class AgentSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        helpers.use_no_llm()

    async def test_unsafe_tool_args_cannot_override_cap_or_schedule(self):
        state = AgentState(mission="Charge the EV", spec={"max_load_kw": 4.6},
                           plan={"schedule": [{"task_id": "ev"}]})
        decision = AgentDecision(thought="test", tool="validate_schedule",
                                 args={"max_load_kw": 999, "schedule": [], "use_live": True})
        args = _safe_args(decision, state, False)
        self.assertEqual(args["max_load_kw"], 4.6)
        self.assertEqual(args["schedule"], [{"task_id": "ev"}])
        self.assertNotIn("use_live", args)

    async def test_ordering_guard_stops_early_optimization(self):
        class EarlyModel:
            def structured(self, *args, **kwargs):
                return AgentDecision(thought="test", tool="optimize_schedule"), []
        decision, origin, notes = await _decide(EarlyModel(), AgentState(mission="EV"), True)
        self.assertEqual(decision.tool, "extract_constraints")
        self.assertEqual(origin, "guardrail")
        self.assertTrue(any("prerequisites" in note for note in notes))

    async def test_final_gate_distrusts_remote_validator(self):
        class TamperedExecutor(DirectExecutor):
            async def call(self, tool, args):
                result = await super().call(tool, args)
                if tool == "optimize_schedule":
                    result["schedule"][0]["power_kw"] = .001
                if tool == "validate_schedule":
                    result["valid"] = True
                return result
        with self.assertRaises(core.InfeasibleMission):
            await run_agent("Charge the EV before 07:00", use_llm=False,
                            executor=TamperedExecutor())

    async def test_no_invented_citation_when_retrieval_empty(self):
        class EmptyRetrieval(DirectExecutor):
            async def call(self, tool, args):
                return [] if tool == "retrieve_evidence" else await super().call(tool, args)
        result = await run_agent("Charge the EV before 07:00", use_llm=False,
                                 executor=EmptyRetrieval())
        self.assertEqual(result["explanation"]["citation_ids"], [])


class AdvancedApiTests(unittest.TestCase):
    def test_impossible_intent_returns_422(self):
        helpers.use_no_llm()
        response = TestClient(app).post("/api/intent", json={
            "prompt": "Charge the EV after 06:00 before 07:00", "use_llm": False})
        self.assertEqual(response.status_code, 422)

    def test_solve_and_calibrate_contracts(self):
        client = TestClient(app)
        response = client.post("/api/planning/solve", json=problem().model_dump())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["validation"]["valid"])
        self.assertEqual(client.post("/api/planning/calibrate", json={
            "forecasts_kw": [[1]] * 9, "actuals_kw": [[1.5]] * 9}).status_code, 200)

    def test_invalid_retrieval_and_impossible_plan_are_422(self):
        client = TestClient(app)
        for top_k in ("bad", -1, 999):
            self.assertEqual(client.post("/api/retrieve", json={"query": "EV", "top_k": top_k}).status_code, 422)
        self.assertEqual(client.post("/api/planning/solve",
                         json=problem(avoid_slots=[0, 1, 2, 3]).model_dump()).status_code, 422)


if __name__ == "__main__":
    unittest.main()
