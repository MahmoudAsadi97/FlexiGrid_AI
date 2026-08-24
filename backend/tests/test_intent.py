"""Mission understanding: rule-based parser, sanitizer, and the LLM path."""

import unittest

from tests import helpers

from flexigrid.intent import (extract_intent, normalize_mission_text,
                              rule_based_spec, sanitize, spec_to_tasks)
from flexigrid.llm import get_llm
from flexigrid.models import MissionSpec, TaskSpec


class RuleParserTests(unittest.TestCase):
    def test_devices_and_deadline(self):
        spec = rule_based_spec("Charge the EV and run the dishwasher before 07:00")
        self.assertEqual(sorted(t.task_id for t in spec.tasks),
                         ["dishwasher", "ev"])
        self.assertTrue(all(t.latest_end == 7 for t in spec.tasks))

    def test_dishwasher_does_not_trigger_laundry(self):
        spec = rule_based_spec("Run the dishwasher before 08:00")
        self.assertEqual([t.task_id for t in spec.tasks], ["dishwasher"])

    def test_evening_does_not_trigger_ev(self):
        spec = rule_based_spec("Preheat the home in the evening by 21:00")
        self.assertEqual([t.task_id for t in spec.tasks], ["heat"])

    def test_avoid_window_parsed(self):
        spec = rule_based_spec("Charge the EV by 23:00 but avoid 17:00 to 20:00")
        self.assertEqual(spec.avoid_hours, [17, 18, 19])

    def test_objective_keywords(self):
        self.assertEqual(rule_based_spec("run laundry cheaply by 9:00").objective,
                         "cost")
        self.assertEqual(rule_based_spec(
            "run laundry by 9:00 and support the grid").objective, "grid")

    def test_capacity_cap_parsed(self):
        spec = rule_based_spec("Charge the EV by 07:00, keep load below 3.6 kW")
        self.assertEqual(spec.max_load_kw, 3.6)

    def test_half_hour_deadline_rounds_up(self):
        spec = rule_based_spec("Preheat the home by 06:30")
        self.assertEqual(spec.tasks[0].latest_end, 7)

    def test_after_constraint_sets_earliest(self):
        spec = rule_based_spec("Charge the EV after 14:00 and before 23:00")
        ev = next(t for t in spec.tasks if t.task_id == "ev")
        self.assertEqual(ev.earliest_start, 14)
        self.assertEqual(ev.latest_end, 23)

    def test_no_device_mention_schedules_full_set(self):
        spec = rule_based_spec("Get everything ready before 07:00 please")
        self.assertEqual(len(spec.tasks), 4)


class SanitizerTests(unittest.TestCase):
    def test_implausible_power_is_reset(self):
        raw = MissionSpec(tasks=[TaskSpec(task_id="ev", power_kw=0.1,
                                          duration_hours=2, earliest_start=0,
                                          latest_end=7)])
        spec, adjustments = sanitize(raw)
        self.assertEqual(spec.tasks[0].power_kw, 3.6)
        self.assertTrue(any("outside plausible range" in a for a in adjustments))

    def test_too_short_window_is_widened(self):
        raw = MissionSpec(tasks=[TaskSpec(task_id="ev", power_kw=3.6,
                                          duration_hours=2, earliest_start=6,
                                          latest_end=7)])
        spec, adjustments = sanitize(raw)
        task = spec.tasks[0]
        self.assertGreaterEqual(task.latest_end - task.earliest_start,
                                task.duration_hours)
        self.assertTrue(adjustments)

    def test_duplicate_tasks_are_dropped(self):
        raw = MissionSpec(tasks=[
            TaskSpec(task_id="ev", power_kw=3.6, duration_hours=2,
                     earliest_start=0, latest_end=7),
            TaskSpec(task_id="ev", power_kw=3.6, duration_hours=2,
                     earliest_start=0, latest_end=7),
        ])
        spec, adjustments = sanitize(raw)
        self.assertEqual(len(spec.tasks), 1)
        self.assertTrue(any("duplicate" in a for a in adjustments))

    def test_spec_to_tasks_maps_catalog_metadata(self):
        spec, _ = sanitize(rule_based_spec("Charge the EV before 07:00"))
        tasks = spec_to_tasks(spec)
        self.assertEqual(tasks[0].source_id, "manual-ev#1")
        self.assertIn("EV", tasks[0].name)


class NormalizationTests(unittest.TestCase):
    """AM/PM handling — a live demo turned 'before 07:00 AM' into evening."""

    def test_ampm_times_rewritten_to_24_hour(self):
        text, changed = normalize_mission_text(
            "Charge the EV before 07:00 AM and preheat by 6:30 pm")
        self.assertTrue(changed)
        self.assertIn("before 07:00", text)
        self.assertIn("by 18:30", text)

    def test_redundant_pm_marker_on_24h_time_is_dropped(self):
        text, _ = normalize_mission_text("Preheat the home by 18:30 PM")
        self.assertIn("by 18:30", text)
        self.assertNotIn("pm", text.lower())

    def test_extract_intent_applies_normalization(self):
        helpers.use_no_llm()
        result = extract_intent("Charge the EV before 07:00 AM",
                                llm=get_llm())
        self.assertEqual(result.spec.tasks[0].latest_end, 7)
        self.assertTrue(any("24-hour" in item for item in result.adjustments))

    def test_degenerate_avoid_hours_are_dropped(self):
        raw = MissionSpec(tasks=[TaskSpec(task_id="ev", power_kw=3.6,
                                          duration_hours=2, earliest_start=0,
                                          latest_end=24)],
                          avoid_hours=list(range(22)))
        spec, adjustments = sanitize(raw)
        self.assertEqual(spec.avoid_hours, [])
        self.assertTrue(any("degenerate" in item for item in adjustments))

    def test_small_avoid_lists_survive_sanitizing(self):
        raw = MissionSpec(tasks=[TaskSpec(task_id="ev", power_kw=3.6,
                                          duration_hours=2, earliest_start=0,
                                          latest_end=24)],
                          avoid_hours=[17, 18, 19])
        spec, _ = sanitize(raw)
        self.assertEqual(spec.avoid_hours, [17, 18, 19])


class LlmIntentTests(unittest.TestCase):
    def test_llm_extraction_via_mock_endpoint(self):
        helpers.use_mock_llm()
        result = extract_intent("Charge the EV before 07:00", llm=get_llm())
        self.assertEqual(result.mode, "llm")
        self.assertEqual(result.spec.tasks[0].task_id, "ev")

    def test_unreachable_endpoint_falls_back_to_rules(self):
        helpers.use_no_llm()
        result = extract_intent("Charge the EV before 07:00", llm=get_llm())
        self.assertEqual(result.mode, "rules")
        self.assertEqual(result.spec.tasks[0].task_id, "ev")


if __name__ == "__main__":
    unittest.main()
