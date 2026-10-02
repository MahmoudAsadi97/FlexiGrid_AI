"""Independent preprocessing, replanning, admission-control and offline contracts."""
import itertools
import math
import random
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from flexigrid.api import app
from flexigrid.embeddings import SbertEmbeddings
from flexigrid.planning import PlanningProblem, PlanningError, NoIncumbentError, solve, validate_starts


def problem(**updates):
    data = dict(jobs=[dict(task_id='a', power_kw=[1.0], earliest_start=0, latest_end=4)],
                slot_minutes=15, tariff_eur_per_kwh=[0.1, 0.2, 0.3, 0.4],
                stress=[50.0]*4, max_load_kw=2.0, objective='cost')
    data.update(updates)
    return PlanningProblem.model_validate(data)


class IndependentBoundaryTests(unittest.TestCase):
    def test_validator_does_not_reuse_solver_candidates(self):
        p = problem(jobs=[dict(task_id='a', power_kw=[1.0], earliest_start=0, latest_end=2)])
        with patch('flexigrid.planning._candidates', return_value=[3]):
            self.assertFalse(validate_starts(p, {'a': 3})['valid'])
            with self.assertRaises(NoIncumbentError):
                solve(p)

    def test_not_before_binds_new_decisions(self):
        p = problem(not_before_slot=2)
        self.assertEqual(solve(p)['starts'], {'a': 2})
        self.assertFalse(validate_starts(p, {'a': 1})['valid'])

    def test_committed_start_survives_replanning(self):
        p = problem(not_before_slot=3, fixed_starts={'a': 0})
        self.assertEqual(solve(p)['starts'], {'a': 0})
        self.assertTrue(validate_starts(p, {'a': 0})['valid'])
        self.assertFalse(validate_starts(p, {'a': 3})['valid'])

    def test_not_before_is_strict_and_bounded(self):
        for value in (-1, 5, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                problem(not_before_slot=value)
        with self.assertRaises(PlanningError):
            solve(problem(not_before_slot=4))

    def test_independent_signed_price_reference_with_replanning(self):
        rng = random.Random(20261002)
        for case in range(60):
            jobs = [dict(task_id=str(i), power_kw=[rng.choice([0.3, 0.8, 1.4])
                    for _ in range(rng.randint(1, 2))], earliest_start=0, latest_end=5) for i in range(3)]
            p = problem(jobs=jobs, tariff_eur_per_kwh=[rng.choice([-0.4, 0.0, 0.3]) for _ in range(5)],
                stress=[40.0]*5, max_load_kw=2.0, background_kw=[0.2]*5, reserve_kw=[0.1]*5,
                not_before_slot=case % 2, avoid_slots=[2] if case % 5 == 0 else [])
            best = math.inf
            for starts in itertools.product(*(range(p.not_before_slot, 6-len(j['power_kw'])) for j in jobs)):
                loads = [0.3]*5
                valid, cost = True, 0.0
                for job, start in zip(jobs, starts):
                    for offset, power in enumerate(job['power_kw']):
                        t = start + offset
                        if t in p.avoid_slots: valid = False
                        loads[t] += power
                        cost += power*p.tariff_eur_per_kwh[t]*0.25
                if valid and max(loads) <= 2.0+1e-9: best = min(best, cost)
            with self.subTest(case=case):
                if math.isfinite(best):
                    self.assertAlmostEqual(solve(p)['validation']['flexible_cost_eur'], best, places=7)
                else:
                    with self.assertRaises(PlanningError): solve(p)

    def test_sentence_transformer_never_downloads_implicitly(self):
        module = ModuleType('sentence_transformers')
        module.SentenceTransformer = Mock()
        with patch.dict(sys.modules, {'sentence_transformers': module}):
            SbertEmbeddings(model='local-test-model')
        module.SentenceTransformer.assert_called_once_with(
            'local-test-model', local_files_only=True, trust_remote_code=False)


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_independent_audit_endpoint(self):
        p = problem().model_dump()
        good = self.client.post('/api/planning/validate', json={'problem': p, 'starts': {'a': 0}})
        self.assertEqual(good.status_code, 200)
        self.assertTrue(good.json()['valid'])
        missing = self.client.post('/api/planning/validate', json={'problem': p, 'starts': {}})
        self.assertFalse(missing.json()['valid'])
        bad = self.client.post('/api/planning/validate', json={'problem': p, 'starts': {'a': False}})
        self.assertEqual(bad.status_code, 422)

    def test_admission_limit_and_release_after_error(self):
        from flexigrid.api import _PLANNING_SLOT
        self.assertTrue(_PLANNING_SLOT.acquire(blocking=False))
        try:
            response = self.client.post('/api/planning/solve', json=problem().model_dump())
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['retry-after'], '1')
        finally:
            _PLANNING_SLOT.release()
        with patch('flexigrid.api.solve', side_effect=NoIncumbentError('test timeout')):
            self.assertEqual(self.client.post('/api/planning/solve', json=problem().model_dump()).status_code, 503)
        self.assertEqual(self.client.post('/api/planning/solve', json=problem().model_dump()).status_code, 200)
