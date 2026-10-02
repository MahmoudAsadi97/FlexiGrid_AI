"""Reproducible synthetic checks, not an estimate of real household savings.

Run: python -m flexigrid.benchmark_planning --output evaluation/planning_results.json
The independent reference below does not call the production objective or validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import time
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import numpy as np
import pydantic
import scipy

from .planning import Job, PlanningError, PlanningProblem, solve
from .uncertainty import CalibrationRequest, calibrate_reserve

SEED = 20261002


def reference_objective(p: PlanningProblem) -> float | None:
    """Independent brute-force specification for small problems only."""
    options = []
    for job in p.jobs:
        options.append([s for s in range(job.earliest_start, job.latest_end-len(job.power_kw)+1)
                        if (job.task_id not in p.fixed_starts or p.fixed_starts[job.task_id] == s)
                        and not any(t in p.avoid_slots for t in range(s, s+len(job.power_kw)))])
    if math.prod(map(len, options)) > 200_000:
        raise ValueError("reference is limited to small instances")
    n = len(p.stress)
    best = math.inf
    for choice in product(*options):
        load = [0.0] * n
        for job, start in zip(p.jobs, choice):
            for offset, power in enumerate(job.power_kw):
                load[start+offset] += power
        if any(load[t] + (p.background_kw or [0]*n)[t] + (p.reserve_kw or [0]*n)[t]
               > p.max_load_kw + 1e-8 for t in range(n)):
            continue
        cost = sum(load[t] * p.tariff_eur_per_kwh[t] * p.slot_minutes/60 for t in range(n))
        grid = sum(load[t] * p.stress[t]/100 * p.slot_minutes/60 for t in range(n))
        value = cost if p.objective == 'cost' else grid if p.objective == 'grid' else (
            p.cost_weight * cost/p.price_scale_eur_per_kwh + (1-p.cost_weight) * grid)
        best = min(best, value)
    return None if best == math.inf else best


def small_problem(rng: np.random.Generator, case: int) -> PlanningProblem:
    return PlanningProblem(
        jobs=[Job(task_id=str(j), power_kw=rng.uniform(.2, 2, rng.integers(1, 4)).tolist(),
                  earliest_start=0, latest_end=6) for j in range(3)],
        slot_minutes=(15, 30, 60)[case % 3],
        tariff_eur_per_kwh=rng.uniform(-.3, .7, 6).tolist(),
        stress=rng.uniform(0, 100, 6).tolist(),
        background_kw=rng.uniform(.1, .5, 6).tolist(), reserve_kw=[.1]*6,
        max_load_kw=(1., 2., 4., 8.)[case % 4],
        avoid_slots=[2] if case % 5 == 0 else [],
        objective=('cost', 'grid', 'balanced')[case % 3])


def wilson(successes: int, n: int) -> list[float]:
    z = 1.959963984540054
    p = successes/n
    centre = (p+z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [round(centre-radius, 4), round(centre+radius, 4)]


def benchmark(cases: int = 200) -> dict:
    rng = np.random.default_rng(SEED)
    feasible = infeasible = 0
    gaps, timings, mismatches = [], [], []
    for case in range(cases):
        p = small_problem(rng, case)
        truth = reference_objective(p)
        started = time.perf_counter()
        try:
            result = solve(p)
            gap = None if truth is None else abs(result['validation']['objective_value']-truth)
            if gap is None or gap > 1e-7 or not result['validation']['valid']:
                mismatches.append(case)
            else:
                feasible += 1
                gaps.append(gap)
        except PlanningError:
            if truth is None:
                infeasible += 1
            else:
                mismatches.append(case)
        timings.append((time.perf_counter()-started)*1000)
    scale = []
    for count in (8, 16, 32, 64):
        p = PlanningProblem(
            jobs=[Job(task_id=str(j), power_kw=rng.uniform(.2, 2, 4).tolist(),
                      earliest_start=0, latest_end=96) for j in range(count)],
            slot_minutes=15, tariff_eur_per_kwh=rng.uniform(.1,.4,96).tolist(),
            stress=[50.]*96, max_load_kw=8., background_kw=[.4]*96,
            reserve_kw=[.3]*96, objective='cost')
        start = time.perf_counter()
        result = solve(p, time_limit_seconds=3)
        scale.append({'jobs': count, 'slots': 96,
                      'elapsed_ms': round((time.perf_counter()-start)*1000, 3),
                      'status': result['solver']['status'], 'mip_gap': result['solver']['mip_gap'],
                      'valid': result['validation']['valid']})
    # Blocks are independent; errors inside a block share a common offset.
    # This is a synthetic fixed forecaster, not a model fitted to Elia/household data.
    rng = np.random.default_rng(SEED + 1)
    forecasts = np.full((1400, 24), .6)
    actual = np.maximum(0, forecasts + rng.normal(0, .03, (1400, 1)) + rng.normal(0, .08, (1400, 24)))
    calibrated = calibrate_reserve(CalibrationRequest(
        forecasts_kw=forecasts[:400].tolist(), actuals_kw=actual[:400].tolist(), alpha=.1))
    q = calibrated['reserve_kw'][0]
    covered = int(np.all(actual[400:] <= forecasts[400:] + q, axis=1).sum())
    shifted = int(np.all(actual[400:] + .2 <= forecasts[400:] + q, axis=1).sum())
    digest = hashlib.sha256()
    for name in ('planning.py', 'uncertainty.py', 'benchmark_planning.py'):
        digest.update(name.encode()); digest.update(Path(__file__).with_name(name).read_bytes())
    return {
        'generated_at': datetime.now(UTC).isoformat(timespec='seconds'),
        'data_source': 'synthetic seeded scenarios, no real household data',
        'seed': SEED, 'source_sha256': digest.hexdigest(),
        'environment': {'python': platform.python_version(), 'numpy': np.__version__,
                        'scipy': scipy.__version__, 'pydantic': pydantic.__version__,
                        'platform': platform.system(), 'machine': platform.machine()},
        'independent_oracle': {'cases': cases, 'feasible_matches': feasible,
            'infeasible_matches': infeasible, 'mismatches': mismatches,
            'max_absolute_objective_gap': max(gaps, default=0),
            'median_solver_ms': round(float(np.median(timings)), 3),
            'p95_solver_ms': round(float(np.quantile(timings, .95)), 3)},
        'scaling': scale,
        'uncertainty': {'calibration_blocks': 400, 'test_blocks': 1000,
            'slots_per_block': 24, 'alpha': .1, 'reserve_kw': round(q, 6),
            'covered_test_blocks': covered, 'whole_block_coverage': covered/1000,
            'wilson_95_interval_conditional_on_this_calibration': wilson(covered, 1000),
            'coverage_after_unmodelled_0_2kw_shift': shifted/1000,
            'limitation': 'Synthetic coverage diagnostic, not evidence of coverage on real time series.'},
        'limitations': ['runtime is environment-specific, not a production SLA',
            'MILP/exhaustive agreement tests implementation, not forecast accuracy',
            'scaling cases have one aggregate cap, not a distribution-network model',
            'no real-model inference, real billing or device actuation measured']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='evaluation/planning_results.json')
    args = parser.parse_args()
    results = benchmark()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(results, indent=2))
    if results['independent_oracle']['mismatches']:
        raise SystemExit('independent reference comparison failed')

if __name__ == '__main__':
    main()
