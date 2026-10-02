"""Time-indexed household scheduling with an independent certificate checker.

One binary variable selects a legal start for each non-interruptible job.
SciPy/HiGHS solves the resulting MILP. A bounded exhaustive solver supplies a
small-instance oracle, not a production fallback. See docs/RESEARCH_UPGRADE.md.
All indices refer to equally spaced elapsed-time slots, not local clock hours.
"""
from __future__ import annotations

import hashlib
import json
import math
from itertools import product
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_matrix

Finite = Annotated[float, Field(allow_inf_nan=False, strict=True)]
NonNegative = Annotated[Finite, Field(ge=0, le=1000)]


class PlanningError(ValueError):
    """Invalid or infeasible scheduling problem."""


class NoIncumbentError(RuntimeError):
    """The solver stopped without a feasible schedule; not proof of infeasibility."""


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=80)
    # Supports appliance cycles with different power in each occupied slot.
    power_kw: list[NonNegative] = Field(min_length=1, max_length=192)
    earliest_start: StrictInt = Field(ge=0)
    latest_end: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def valid_window(self):
        if self.latest_end - self.earliest_start < len(self.power_kw):
            raise ValueError("task duration does not fit its window")
        if sum(self.power_kw) <= 0:
            raise ValueError("a task must consume positive energy")
        return self


class PlanningProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[Job] = Field(min_length=1, max_length=64)
    slot_minutes: Literal[15, 30, 60] = 60
    tariff_eur_per_kwh: list[Finite] = Field(min_length=1, max_length=192)
    stress: list[Annotated[Finite, Field(ge=0, le=100)]]
    max_load_kw: Finite = Field(gt=0, le=1000)
    background_kw: list[NonNegative] | None = None
    reserve_kw: list[NonNegative] | None = None
    avoid_slots: list[StrictInt] = Field(default_factory=list, max_length=192)
    fixed_starts: dict[str, StrictInt] = Field(default_factory=dict)
    # New decisions cannot start before this elapsed-time slot; fixed starts may.
    not_before_slot: StrictInt = Field(default=0, ge=0, le=192)
    objective: Literal["cost", "grid", "balanced"] = "balanced"
    cost_weight: Finite = Field(default=0.56, ge=0, le=1)
    price_scale_eur_per_kwh: Finite = Field(default=0.30, gt=0, le=1000)

    @model_validator(mode="after")
    def consistent(self):
        n = len(self.tariff_eur_per_kwh)
        if self.not_before_slot > n:
            raise ValueError("not_before_slot is outside the horizon")
        if max(abs(x) for x in self.tariff_eur_per_kwh) > 1000:
            raise ValueError("tariff is outside the supported numerical range")
        for name in ("stress", "background_kw", "reserve_kw"):
            values = getattr(self, name)
            if values is not None and len(values) != n:
                raise ValueError(f"{name} must have {n} slots")
        ids = [job.task_id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("task IDs must be unique")
        if set(self.fixed_starts) - set(ids):
            raise ValueError("fixed_starts contains an unknown task")
        if any(t < 0 or t >= n for t in self.avoid_slots):
            raise ValueError("avoid slot is outside the horizon")
        for job in self.jobs:
            if job.latest_end > n:
                raise ValueError("task window is outside the horizon")
            fixed = self.fixed_starts.get(job.task_id)
            if fixed is not None and not (
                job.earliest_start <= fixed <= job.latest_end - len(job.power_kw)
            ):
                raise ValueError("fixed start is outside the task window")
        return self


def unit_scores(problem: PlanningProblem) -> np.ndarray:
    """Cost is actual EUR; grid is stress-weighted kWh, not emissions."""
    price = np.asarray(problem.tariff_eur_per_kwh, dtype=float)
    stress = np.asarray(problem.stress, dtype=float) / 100
    if problem.objective == "cost":
        return price
    if problem.objective == "grid":
        return stress
    w = problem.cost_weight
    return w * price / problem.price_scale_eur_per_kwh + (1 - w) * stress


def _candidates(problem: PlanningProblem, job: Job) -> list[int]:
    starts = range(job.earliest_start, job.latest_end - len(job.power_kw) + 1)
    blocked = set(problem.avoid_slots)
    fixed = problem.fixed_starts.get(job.task_id)
    return [s for s in starts if (fixed is None or fixed == s)
            and (fixed is not None or s >= problem.not_before_slot)
            and not blocked.intersection(range(s, s + len(job.power_kw)))]


def validate_starts(problem: PlanningProblem, starts: dict[str, int]) -> dict:
    """Reconstruct power from the ORIGINAL jobs, never from solver metadata."""
    n = len(problem.tariff_eur_per_kwh)
    errors: list[str] = []
    ids = {job.task_id for job in problem.jobs}
    if set(starts) != ids:
        errors.append("missing or unexpected task IDs")
    flexible = np.zeros(n)
    for job in problem.jobs:
        s = starts.get(job.task_id)
        # Do not reuse _candidates: a bug in solver preprocessing must not also
        # become a bug in the independent checker.
        fixed = problem.fixed_starts.get(job.task_id)
        duration = len(job.power_kw)
        valid = (type(s) is int and 0 <= s and s + duration <= n
                 and s >= job.earliest_start and s + duration <= job.latest_end)
        if valid:
            valid = (s == fixed if fixed is not None else s >= problem.not_before_slot)
        if valid:
            valid = not set(problem.avoid_slots).intersection(range(s, s + duration))
        if not valid:
            errors.append(f"invalid start for {job.task_id}")
            continue
        flexible[s:s + duration] += job.power_kw
    background = np.asarray(problem.background_kw or [0.] * n)
    reserve = np.asarray(problem.reserve_kw or [0.] * n)
    forecast_load = flexible + background
    protected = forecast_load + reserve
    if np.any(protected > problem.max_load_kw + 1e-7):
        errors.append("capacity including background and reserve exceeded")
    dt = problem.slot_minutes / 60
    return {
        "valid": not errors, "errors": errors,
        "flexible_load_kw": flexible.tolist(),
        "forecast_total_load_kw": forecast_load.tolist(),
        "reserved_total_load_kw": protected.tolist(),
        "peak_load_kw": float(protected.max()),
        "flexible_energy_kwh": float(flexible.sum() * dt),
        "flexible_cost_eur": float(flexible @ problem.tariff_eur_per_kwh * dt),
        "forecast_total_cost_eur": float(forecast_load @ problem.tariff_eur_per_kwh * dt),
        "objective_value": float(flexible @ unit_scores(problem) * dt),
        "capacity_scope": ("forecast-background-plus-flexible-and-reserve"
                           if problem.background_kw is not None else "flexible-plus-reserve-only"),
    }


def solve(problem: PlanningProblem, *, backend: Literal["milp", "exact"] = "milp",
          time_limit_seconds: float = 10.0, max_exact_combinations: int = 200_000) -> dict:
    """Return a checked solution and solver status, or raise a typed error.

    Avoid slots are HARD constraints here. There is no silent relaxation.
    Status 1 with an incumbent is reported as feasible, not optimal.
    """
    # Revalidate even a caller-created model copy before numerical computation.
    problem = PlanningProblem.model_validate(problem.model_dump())
    if not math.isfinite(time_limit_seconds) or not 0 < time_limit_seconds <= 60:
        raise ValueError("time limit must be in (0, 60] seconds")
    if backend not in ("milp", "exact"):
        raise ValueError("unknown solver backend")
    candidates = [_candidates(problem, job) for job in problem.jobs]
    if any(not values for values in candidates):
        raise PlanningError("a task has no legal start under the hard constraints")
    dt = problem.slot_minutes / 60
    scores = unit_scores(problem)
    costs = [[float(np.asarray(job.power_kw) @ scores[s:s+len(job.power_kw)] * dt)
              for s in values] for job, values in zip(problem.jobs, candidates)]
    n = len(problem.tariff_eur_per_kwh)
    capacity = (problem.max_load_kw - np.asarray(problem.background_kw or [0.] * n)
                - np.asarray(problem.reserve_kw or [0.] * n))
    if np.any(capacity < -1e-7):
        raise PlanningError("background and reserve alone exceed the capacity cap")

    if backend == "exact":
        combinations = math.prod(len(values) for values in candidates)
        if combinations > min(max_exact_combinations, 200_000):
            raise ValueError("exact oracle budget exceeded; use the MILP backend")
        best, starts = float("inf"), None
        # Full enumeration is deliberate: negative future costs cannot break pruning.
        for choice in product(*candidates):
            proposal = dict(zip((j.task_id for j in problem.jobs), choice))
            check = validate_starts(problem, proposal)
            if check["valid"] and check["objective_value"] < best:
                best, starts = check["objective_value"], proposal
        if starts is None:
            raise PlanningError("no feasible schedule")
        metadata = {"backend": "exhaustive-oracle", "status": "optimal",
                    "mip_gap": 0.0, "dual_bound": best}
    else:
        columns = [(i, s) for i, values in enumerate(candidates) for s in values]
        c = np.asarray([value for row in costs for value in row])
        rows, cols, data = [], [], []
        for col, (i, start) in enumerate(columns):
            rows.append(i); cols.append(col); data.append(1.0)
            for offset, power in enumerate(problem.jobs[i].power_kw):
                rows.append(len(problem.jobs) + start + offset)
                cols.append(col); data.append(power)
        matrix = csc_matrix((data, (rows, cols)), shape=(len(problem.jobs) + n, len(c)))
        lower = np.r_[np.ones(len(problem.jobs)), np.full(n, -np.inf)]
        upper = np.r_[np.ones(len(problem.jobs)), capacity]
        result = milp(c=c, integrality=np.ones(len(c)), bounds=Bounds(0, 1),
                      constraints=LinearConstraint(matrix, lower, upper),
                      options={"time_limit": time_limit_seconds, "mip_rel_gap": 0.0})
        if result.status == 2:
            raise PlanningError("solver proved the mission infeasible")
        if result.status not in (0, 1) or result.x is None:
            raise NoIncumbentError(f"solver stopped without a schedule (status {result.status})")
        x = np.asarray(result.x)
        if (x.shape != c.shape or not np.all(np.isfinite(x))
                or np.any(x < -1e-6) or np.any(x > 1 + 1e-6)
                or np.any(np.abs(x - np.rint(x)) > 1e-6)):
            raise NoIncumbentError("solver did not return an integer incumbent")
        starts = {}
        for selected, (i, start) in zip(x > 0.5, columns):
            if selected:
                task_id = problem.jobs[i].task_id
                if task_id in starts:
                    raise NoIncumbentError("solver selected a task more than once")
                starts[task_id] = start
        def optional_number(name):
            value = getattr(result, name, None)
            return float(value) if value is not None and math.isfinite(value) else None
        metadata = {"backend": "scipy-highs-milp",
                    "status": "optimal" if result.status == 0 else "feasible-time-limit",
                    "mip_gap": optional_number("mip_gap"),
                    "dual_bound": optional_number("mip_dual_bound")}
    validation = validate_starts(problem, starts)
    if not validation["valid"]:
        raise NoIncumbentError("independent validation rejected the solver output")
    fingerprint = hashlib.sha256(json.dumps(problem.model_dump(), sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    return {"starts": starts, "validation": validation, "solver": metadata,
            "problem_sha256": fingerprint, "slot_minutes": problem.slot_minutes,
            "advisory_only": True,
            "assumptions": ["slot-average power, not instantaneous electrical protection",
                            "non-interruptible tasks with known power profiles",
                            "stress is a relative index, not carbon intensity",
                            "equal elapsed-time slots; caller aligns timestamps"]}
