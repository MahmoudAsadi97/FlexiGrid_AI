"""Deterministic planning core.

The optimizer is intentionally *not* a language model. Exact time-window,
deadline, and capacity constraints are represented and tested as code; the
LLM layers around this core interpret missions and explain results, but they
never decide feasibility.

Two optimizers are provided:

- ``optimize``        — time-indexed MILP; independently checked before return.
                        The planning module also provides a bounded exact oracle.
- ``greedy_optimize`` — places each task independently at its locally best
                        hour. Kept as an ablation: it reproduces the failure
                        mode that motivated the joint search.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from .planning import Job, PlanningProblem, PlanningError, solve
from typing import Literal, Sequence

Objective = Literal["balanced", "cost", "grid"]

# Frozen 24-hour demo fixture (see backend/data/elia_demo_snapshot.json).
# Live derivation of the stress series is implemented in derive.py.
TARIFF = [
    0.22, 0.18, 0.16, 0.15, 0.14, 0.15, 0.19, 0.27, 0.31, 0.29, 0.25, 0.23,
    0.21, 0.20, 0.22, 0.28, 0.37, 0.46, 0.42, 0.34, 0.28, 0.24, 0.21, 0.19,
]

GRID_STRESS = [
    48, 42, 38, 34, 31, 33, 45, 59, 71, 76, 68, 55,
    42, 35, 29, 32, 51, 78, 91, 86, 70, 58, 52, 47,
]

_COST_WEIGHT = {"cost": 1.0, "grid": 0.0, "balanced": 0.56}

EPSILON = 1e-9


@dataclass(frozen=True)
class Task:
    task_id: str
    name: str
    power_kw: float
    duration_hours: int
    earliest_start: int
    latest_end: int
    source_id: str


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    name: str
    power_kw: float
    duration_hours: int
    earliest_start: int
    latest_end: int
    source_id: str
    start: int
    end: int
    cost_eur: float
    grid_stress: int


class InfeasibleMission(ValueError):
    """No schedule satisfies the supplied constraints."""


def _slot_score(task: Task, start: int, objective: Objective,
                tariff: Sequence[float], stress: Sequence[float]) -> float:
    cost_weight = _COST_WEIGHT[objective]
    # A fixed scale keeps blended scores comparable across days, including
    # days with zero or negative prices. Cost/grid modes are pure objectives.
    scale = 0.30 if objective == "balanced" else 1.0
    return sum(task.power_kw * (
        cost_weight * tariff[h] / scale + (1 - cost_weight) * stress[h] / 100)
        for h in range(start, start + task.duration_hours))


def _metrics(task: Task, start: int, tariff: Sequence[float],
             stress: Sequence[float]) -> tuple[float, int]:
    hours = range(start, start + task.duration_hours)
    cost = sum(task.power_kw * tariff[hour] for hour in hours)
    average_stress = round(sum(stress[hour] for hour in hours) / task.duration_hours)
    return round(cost, 2), average_stress


def _candidate_starts(task: Task, avoid_hours: frozenset[int]) -> list[int]:
    starts = []
    for start in range(task.earliest_start, task.latest_end - task.duration_hours + 1):
        occupied = range(start, start + task.duration_hours)
        if avoid_hours and any(hour in avoid_hours for hour in occupied):
            continue
        starts.append(start)
    return starts


def _finalize(tasks: Sequence[Task], starts: dict[str, int],
              tariff: Sequence[float], stress: Sequence[float]) -> list[ScheduledTask]:
    scheduled = []
    for task in tasks:
        start = starts[task.task_id]
        cost, average_stress = _metrics(task, start, tariff, stress)
        scheduled.append(ScheduledTask(
            **asdict(task), start=start, end=start + task.duration_hours,
            cost_eur=cost, grid_stress=average_stress,
        ))
    return scheduled


def optimize_detailed(tasks: list[Task], objective: Objective,
                      max_load_kw: float = 4.6,
                      tariff: Sequence[float] | None = None,
                      stress: Sequence[float] | None = None,
                      avoid_hours: Sequence[int] = (), *,
                      backend: Literal["milp", "exact"] = "milp") -> tuple[list[ScheduledTask], dict]:
    """Hourly compatibility adapter to the time-indexed planning engine.

    Legacy avoid-hours remain a soft preference and relaxation is reported.
    The advanced PlanningProblem API instead treats avoid_slots as hard.
    """
    prices = list(TARIFF if tariff is None else tariff)
    signal = list(GRID_STRESS if stress is None else stress)
    if len(prices) != 24 or len(signal) != 24:
        raise ValueError("the legacy hourly API requires exactly 24 slots")
    ordered = sorted(tasks, key=lambda t: (
        t.latest_end - t.earliest_start - t.duration_hours, -t.power_kw, t.task_id))
    jobs = []
    for task in ordered:
        if type(task.duration_hours) is not int or task.duration_hours < 1:
            raise ValueError("duration must be a positive integer")
        # A too-short user mission is infeasible, not an internal server error.
        if task.latest_end - task.earliest_start < task.duration_hours:
            raise InfeasibleMission("task duration does not fit its window")
        jobs.append(Job(task_id=task.task_id,
                        power_kw=[task.power_kw] * task.duration_hours,
                        earliest_start=task.earliest_start, latest_end=task.latest_end))
    problem = PlanningProblem(jobs=jobs, tariff_eur_per_kwh=prices,
                              stress=signal, max_load_kw=max_load_kw,
                              objective=objective, avoid_slots=list(avoid_hours))
    relaxed = False
    try:
        result = solve(problem, backend=backend)
    except PlanningError as error:
        if not avoid_hours:
            raise InfeasibleMission(str(error)) from error
        relaxed = True
        try:
            result = solve(problem.model_copy(update={"avoid_slots": []}), backend=backend)
        except PlanningError as second:
            raise InfeasibleMission(str(second)) from second
    metadata = {**result["solver"], "problem_sha256": result["problem_sha256"],
                "avoid_hours_relaxed": relaxed}
    return _finalize(ordered, result["starts"], prices, signal), metadata


def optimize(tasks: list[Task], objective: Objective,
             max_load_kw: float = 4.6,
             tariff: Sequence[float] | None = None,
             stress: Sequence[float] | None = None,
             avoid_hours: Sequence[int] = ()) -> list[ScheduledTask]:
    return optimize_detailed(tasks, objective, max_load_kw, tariff, stress, avoid_hours)[0]


def greedy_optimize(tasks: list[Task], objective: Objective,
                    max_load_kw: float = 4.6,
                    tariff: Sequence[float] | None = None,
                    stress: Sequence[float] | None = None) -> list[ScheduledTask]:
    """Ablation baseline: per-task local choice, no joint search, no backtracking."""
    tariff = TARIFF if tariff is None else tariff
    stress = GRID_STRESS if stress is None else stress
    load = [0.0] * 24
    starts: dict[str, int] = {}
    for task in tasks:  # given order — greedy is order-sensitive by design
        candidates = sorted(
            _candidate_starts(task, frozenset()),
            key=lambda start: (_slot_score(task, start, objective, tariff, stress), start),
        )
        placed = False
        for start in candidates:
            hours = range(start, start + task.duration_hours)
            if all(load[hour] + task.power_kw <= max_load_kw + EPSILON for hour in hours):
                starts[task.task_id] = start
                for hour in hours:
                    load[hour] += task.power_kw
                placed = True
                break
        if not placed:
            raise InfeasibleMission(
                f"Greedy placement failed for task '{task.task_id}'")
    return _finalize(tasks, starts, tariff, stress)


def earliest_start_schedule(tasks: list[Task], max_load_kw: float = 4.6,
                            tariff: Sequence[float] | None = None,
                            stress: Sequence[float] | None = None) -> list[ScheduledTask]:
    """Naive comparison baseline: everything as early as capacity allows."""
    tariff = TARIFF if tariff is None else tariff
    stress = GRID_STRESS if stress is None else stress
    load = [0.0] * 24
    starts: dict[str, int] = {}
    for task in tasks:
        placed = False
        for start in range(task.earliest_start, task.latest_end - task.duration_hours + 1):
            hours = range(start, start + task.duration_hours)
            if all(load[hour] + task.power_kw <= max_load_kw + EPSILON for hour in hours):
                starts[task.task_id] = start
                for hour in hours:
                    load[hour] += task.power_kw
                placed = True
                break
        if not placed:
            raise InfeasibleMission(
                f"Earliest-start baseline failed for task '{task.task_id}'")
    return _finalize(tasks, starts, tariff, stress)


def validate(schedule: list[ScheduledTask], max_load_kw: float = 4.6,
             avoid_hours: Sequence[int] = (),
             expected_tasks: Sequence[Task] | None = None) -> dict[str, object]:
    """Fail-closed critic, optionally bound to the original mission tasks."""
    errors: list[str] = []
    load = [0.0] * 24
    avoid = set(avoid_hours)
    cap_ok = (isinstance(max_load_kw, (float, int)) and not isinstance(max_load_kw, bool)
              and math.isfinite(max_load_kw) and max_load_kw > 0)
    if not cap_ok:
        errors.append("invalid capacity")
    if any(type(h) is not int or not 0 <= h < 24 for h in avoid):
        errors.append("invalid avoid-hour index")
    ids = [t.task_id for t in schedule]
    if not ids or len(ids) != len(set(ids)):
        errors.append("empty schedule or duplicate task IDs")
    expected = {t.task_id: t for t in expected_tasks} if expected_tasks is not None else None
    if expected is not None and (set(ids) != set(expected) or len(expected) != len(expected_tasks)):
        errors.append("schedule task IDs do not match the mission")
    within_windows, avoid_respected, per_task = True, True, []
    for task in schedule:
        shape_ok = (all(type(v) is int for v in (task.start, task.end,
                         task.earliest_start, task.latest_end, task.duration_hours))
                    and 0 <= task.start < task.end <= 24
                    and 0 <= task.earliest_start < task.latest_end <= 24
                    and task.duration_hours > 0
                    and task.end - task.start == task.duration_hours
                    and isinstance(task.power_kw, (float, int))
                    and not isinstance(task.power_kw, bool)
                    and math.isfinite(task.power_kw) and task.power_kw > 0)
        reference = expected.get(task.task_id) if expected is not None else None
        matches = expected is None or (reference is not None and all(
            getattr(task, field) == getattr(reference, field)
            for field in ("power_kw", "duration_hours", "earliest_start", "latest_end", "source_id")))
        window_ok = bool(shape_ok and task.start >= task.earliest_start and task.end <= task.latest_end)
        within_windows = within_windows and window_ok
        if not shape_ok or not matches:
            errors.append(f"invalid or altered task: {task.task_id}")
        if shape_ok:
            for h in range(task.start, task.end):
                load[h] += task.power_kw
                if h in avoid:
                    avoid_respected = False
        per_task.append({"task_id": task.task_id, "within_window": window_ok,
                         "matches_mission": matches})
    below_capacity = bool(cap_ok and all(v <= max_load_kw + EPSILON for v in load))
    return {"valid": not errors and within_windows and below_capacity,
            "errors": errors, "within_windows": within_windows,
            "below_capacity": below_capacity, "avoid_hours_respected": avoid_respected,
            "peak_load_kw": round(max(load), 2), "hourly_load_kw": [round(v, 2) for v in load],
            "per_task": per_task, "max_load_kw": max_load_kw,
            "mission_bound": expected_tasks is not None,
            "capacity_scope": "controllable-load-only"}


def demo_tasks() -> list[Task]:
    return [
        Task("heat", "Heat-pump preheat", 1.4, 2, 3, 7, "manual-heatpump#0"),
        Task("dishwasher", "Dishwasher · Eco 50 °C", 0.5, 2, 0, 7, "manual-dishwasher#0"),
        Task("ev", "EV charge · eco mode", 3.6, 2, 0, 7, "manual-ev#1"),
        Task("laundry", "Washing machine · 40 °C", 0.8, 1, 0, 7, "manual-washer#0"),
    ]


def plan_to_dict(schedule: list[ScheduledTask], objective: Objective,
                 max_load_kw: float = 4.6,
                 avoid_hours: Sequence[int] = (),
                 tariff: Sequence[float] | None = None,
                 expected_tasks: Sequence[Task] | None = None) -> dict[str, object]:
    validation = validate(schedule, max_load_kw, avoid_hours, expected_tasks)
    energy = sum(t.power_kw * t.duration_hours for t in schedule)
    total_cost = (sum(t.power_kw * sum(tariff[t.start:t.end]) for t in schedule)
                  if tariff is not None else sum(t.cost_eur for t in schedule))
    return {
        "objective": objective,
        "schedule": [asdict(task) for task in schedule],
        "validation": validation,
        "total_cost_eur": round(total_cost, 2),
        "average_grid_stress": round(
            sum(t.grid_stress * t.power_kw * t.duration_hours for t in schedule) / energy) if energy else 0,
        "total_energy_kwh": round(energy, 6),
        "unweighted_task_stress": round(
            sum(t.grid_stress for t in schedule) / max(len(schedule), 1)),
        "peak_load_kw": validation["peak_load_kw"],
    }


def create_demo_plan(objective: Objective = "balanced") -> dict[str, object]:
    schedule = optimize(demo_tasks(), objective)
    return plan_to_dict(schedule, objective)
