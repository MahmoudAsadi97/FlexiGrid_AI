"""Planner core: optimizers, validator, baselines, fixtures."""

import json
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401  (sets deterministic env)

from flexigrid import core
from flexigrid.core import (InfeasibleMission, Task, create_demo_plan,
                            demo_tasks, earliest_start_schedule,
                            greedy_optimize, optimize, validate)

DATA = Path(__file__).resolve().parent.parent / "data"


class OptimizerTests(unittest.TestCase):
    def test_all_objectives_are_feasible(self):
        for objective in ("balanced", "cost", "grid"):
            with self.subTest(objective=objective):
                schedule = optimize(demo_tasks(), objective)
                result = validate(schedule)
                self.assertTrue(result["valid"])
                self.assertLessEqual(result["peak_load_kw"], 4.6)

    def test_plan_is_reproducible(self):
        self.assertEqual(create_demo_plan("balanced"), create_demo_plan("balanced"))

    def test_infeasible_mission_raises(self):
        tasks = [
            Task("a", "Load A", 3.6, 1, 5, 6, "policy-capacity#1"),
            Task("b", "Load B", 3.6, 1, 5, 6, "policy-capacity#1"),
        ]
        with self.assertRaises(InfeasibleMission):
            optimize(tasks, "balanced")

    def test_optimizer_beats_or_matches_earliest_start_on_cost(self):
        for objective in ("cost", "balanced"):
            schedule = optimize(demo_tasks(), objective)
            baseline = earliest_start_schedule(demo_tasks())
            self.assertLessEqual(sum(t.cost_eur for t in schedule),
                                 sum(t.cost_eur for t in baseline) + 1e-9)

    def test_avoid_hours_are_respected_when_feasible(self):
        tasks = [Task("ev", "EV", 3.6, 2, 14, 23, "manual-ev#1")]
        schedule = optimize(tasks, "cost", avoid_hours=[17, 18, 19])
        occupied = set(range(schedule[0].start, schedule[0].end))
        self.assertFalse(occupied & {17, 18, 19})
        self.assertTrue(validate(schedule, avoid_hours=[17, 18, 19])
                        ["avoid_hours_respected"])

    def test_impossible_avoid_hours_relax_instead_of_failing(self):
        tasks = [Task("ev", "EV", 3.6, 2, 17, 20, "manual-ev#1")]
        schedule = optimize(tasks, "cost", avoid_hours=[17, 18, 19])
        self.assertEqual(len(schedule), 1)  # relaxed, not raised

    def test_custom_tariff_changes_the_chosen_slot(self):
        tasks = [Task("ev", "EV", 3.6, 1, 0, 6, "manual-ev#1")]
        cheap_at_2 = [1.0] * 24
        cheap_at_2[2] = 0.01
        schedule = optimize(tasks, "cost", tariff=cheap_at_2,
                            stress=[50] * 24)
        self.assertEqual(schedule[0].start, 2)

    def test_validator_rejects_capacity_violation(self):
        good = optimize(demo_tasks(), "balanced")
        result = validate(good, max_load_kw=1.0)  # tighten the cap after the fact
        self.assertFalse(result["valid"])
        self.assertFalse(result["below_capacity"])

    def test_validator_rejects_window_violation(self):
        schedule = optimize(demo_tasks(), "balanced")
        broken = [core.ScheduledTask(**{**vars(schedule[0]),
                                        "start": 20, "end": 22})] + schedule[1:]
        self.assertFalse(validate(broken)["within_windows"])


class GreedyAblationTests(unittest.TestCase):
    def test_greedy_fails_on_tight_windows_where_joint_succeeds(self):
        tight = [
            Task("ev", "EV", 3.6, 2, 0, 4, "manual-ev#1"),
            Task("heat", "Heat", 1.4, 2, 2, 4, "manual-heatpump#0"),
        ]
        joint = optimize(tight, "cost")
        self.assertTrue(validate(joint)["valid"])
        with self.assertRaises(InfeasibleMission):
            greedy_optimize(tight, "cost")

    def test_greedy_never_exceeds_capacity_when_it_succeeds(self):
        tasks = [Task("dw", "DW", 0.5, 2, 0, 8, "manual-dishwasher#0"),
                 Task("wm", "WM", 0.8, 1, 0, 8, "manual-washer#0")]
        schedule = greedy_optimize(tasks, "balanced")
        self.assertTrue(validate(schedule)["valid"])


class FixtureTests(unittest.TestCase):
    def test_frozen_elia_fixture_is_explicitly_labelled(self):
        snapshot = json.loads((DATA / "elia_demo_snapshot.json").read_text())
        self.assertEqual(snapshot["mode"], "frozen-demo-fixture")
        self.assertIn("not asserted as a live Elia record", snapshot["warning"])
        self.assertEqual(set(snapshot["dataset_contracts"]),
                         {"ods002", "ods086", "ods201"})

    def test_demo_task_sources_exist_in_corpus(self):
        from flexigrid.ingest import load_corpus
        chunk_ids = {chunk.chunk_id for chunk in load_corpus()}
        for task in demo_tasks():
            self.assertIn(task.source_id, chunk_ids)


if __name__ == "__main__":
    unittest.main()
