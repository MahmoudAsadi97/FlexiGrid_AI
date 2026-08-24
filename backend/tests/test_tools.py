"""Tool registry behaviours that sit above the core planner."""

import unittest

from tests import helpers  # noqa: F401

from flexigrid.models import MissionSpec, TaskSpec
from flexigrid.tools import optimize_schedule, validate_schedule


def _pinned_heat_spec() -> dict:
    """A mission whose naive earliest-start baseline is infeasible.

    The heat pump is pinned to exactly [0, 2). A greedy earliest-start pass
    fills hours 0-2 with the EV and dishwasher first and then cannot place
    the heat pump; joint constrained search places the heat pump first and
    succeeds. Regression test for the live-demo failure where this raised
    instead of being reported.
    """
    return MissionSpec(tasks=[
        TaskSpec(task_id="ev", power_kw=3.6, duration_hours=2,
                 earliest_start=0, latest_end=9),
        TaskSpec(task_id="dishwasher", power_kw=0.5, duration_hours=2,
                 earliest_start=0, latest_end=9),
        TaskSpec(task_id="laundry", power_kw=0.8, duration_hours=1,
                 earliest_start=0, latest_end=9),
        TaskSpec(task_id="heat", power_kw=1.4, duration_hours=2,
                 earliest_start=0, latest_end=2),
    ], objective="cost", max_load_kw=4.6).model_dump()


class OptimizeScheduleToolTests(unittest.TestCase):
    def test_infeasible_baseline_is_reported_not_raised(self):
        plan = optimize_schedule(spec=_pinned_heat_spec())
        self.assertTrue(plan["validation"]["valid"])
        self.assertIsNone(plan["baseline"])
        self.assertIn("earliest-start baseline", plan["baseline_note"])
        heat = next(task for task in plan["schedule"]
                    if task["task_id"] == "heat")
        self.assertEqual((heat["start"], heat["end"]), (0, 2))

    def test_normal_mission_still_carries_a_baseline(self):
        plan = optimize_schedule(spec=None, objective="balanced")
        self.assertIsNotNone(plan["baseline"])
        self.assertNotIn("baseline_note", plan)

    def test_validate_schedule_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            validate_schedule([])


if __name__ == "__main__":
    unittest.main()
