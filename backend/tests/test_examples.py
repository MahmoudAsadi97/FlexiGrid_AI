"""The documented HTTP request must remain a runnable example."""
from pathlib import Path
import unittest

from flexigrid.planning import PlanningProblem, solve


class DocumentedExampleTests(unittest.TestCase):
    def test_repository_planning_example(self):
        path = Path(__file__).resolve().parents[2] / "examples" / "planning_problem.json"
        problem = PlanningProblem.model_validate_json(path.read_text(encoding="utf-8"))
        result = solve(problem)
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(set(result["starts"]), {job.task_id for job in problem.jobs})
        self.assertTrue(result["advisory_only"])
