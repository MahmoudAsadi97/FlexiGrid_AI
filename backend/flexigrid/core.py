"""Deterministic planning core.

The optimizer is intentionally *not* a language model. Exact time-window,
deadline, and capacity constraints are represented and tested as code; the
LLM layers around this core interpret missions and explain results, but they
never decide feasibility.

Two optimizers are provided:

- ``optimize``        — exhaustive joint constrained search with pruning
                        (branch-and-bound). Optimal for the small daily
                        problem; acts as the oracle in the evaluation.
- ``greedy_optimize`` — places each task independently at its locally best
                        hour. Kept as an ablation: it reproduces the failure
                        mode that motivated the joint search.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

_COST_WEIGHT = {"cost": 0.84, "grid": 0.18, "balanced": 0.56}

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
    max_price = max(tariff)
    score = 0.0
    for hour in range(start, start + task.duration_hours):
        score += cost_weight * (tariff[hour] / max_price)
        score += (1 - cost_weight) * (stress[hour] / 100)
    return score


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


def optimize(tasks: list[Task], objective: Objective,
             max_load_kw: float = 4.6,
             tariff: Sequence[float] | None = None,
             stress: Sequence[float] | None = None,
             avoid_hours: Sequence[int] = ()) -> list[ScheduledTask]:
    """Exhaustive joint constrained search with branch-and-bound pruning."""
    tariff = tariff or TARIFF
    stress = stress or GRID_STRESS
    avoid = frozenset(int(hour) % 24 for hour in avoid_hours)

    load = [0.0] * 24
    best_score = float("inf")
    best_starts: dict[str, int] | None = None
    # Most-constrained-first ordering shrinks the search tree.
    ordered = sorted(tasks, key=lambda task: (
        task.latest_end - task.earliest_start - task.duration_hours,
        -task.power_kw,
        task.task_id,
    ))

    def search(index: int, score: float, starts: dict[str, int]) -> None:
        nonlocal best_score, best_starts
        if score >= best_score:
            return
        if index == len(ordered):
            best_score = score
            best_starts = dict(starts)
            return
        task = ordered[index]
        candidates = sorted(
            _candidate_starts(task, avoid),
            key=lambda start: (_slot_score(task, start, objective, tariff, stress), start),
        )
        for start in candidates:
            hours = range(start, start + task.duration_hours)
            if not all(load[hour] + task.power_kw <= max_load_kw + EPSILON for hour in hours):
                continue
            for hour in hours:
                load[hour] += task.power_kw
            starts[task.task_id] = start
            search(index + 1,
                   score + _slot_score(task, start, objective, tariff, stress), starts)
            del starts[task.task_id]
            for hour in hours:
                load[hour] -= task.power_kw
    search(0, 0.0, {})

    if best_starts is None:
        if avoid:
            # The avoid-window preference made the mission impossible; relax it
            # rather than fail. Callers surface the relaxation in the trace.
            relaxed = optimize(tasks, objective, max_load_kw, tariff, stress, ())
            return relaxed
        raise InfeasibleMission("No feasible schedule for the supplied constraints")
    return _finalize(ordered, best_starts, tariff, stress)


def greedy_optimize(tasks: list[Task], objective: Objective,
                    max_load_kw: float = 4.6,
                    tariff: Sequence[float] | None = None,
                    stress: Sequence[float] | None = None) -> list[ScheduledTask]:
    """Ablation baseline: per-task local choice, no joint search, no backtracking."""
    tariff = tariff or TARIFF
    stress = stress or GRID_STRESS
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
    tariff = tariff or TARIFF
    stress = stress or GRID_STRESS
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
             avoid_hours: Sequence[int] = ()) -> dict[str, object]:
    """Independent critic: re-checks a schedule from scratch."""
    avoid = frozenset(int(hour) % 24 for hour in avoid_hours)
    load = [0.0] * 24
    within_windows = True
    avoid_respected = True
    per_task: list[dict[str, object]] = []
    for task in schedule:
        window_ok = task.start >= task.earliest_start and task.end <= task.latest_end
        within_windows = within_windows and window_ok
        occupied = list(range(task.start, task.end))
        if avoid and any(hour in avoid for hour in occupied):
            avoid_respected = False
        for hour in occupied:
            load[hour] += task.power_kw
        per_task.append({"task_id": task.task_id, "within_window": window_ok})
    below_capacity = all(value <= max_load_kw + EPSILON for value in load)
    return {
        "valid": within_windows and below_capacity,
        "within_windows": within_windows,
        "below_capacity": below_capacity,
        "avoid_hours_respected": avoid_respected,
        "peak_load_kw": round(max(load), 2),
        "hourly_load_kw": [round(value, 2) for value in load],
        "per_task": per_task,
        "max_load_kw": max_load_kw,
    }


def demo_tasks() -> list[Task]:
    return [
        Task("heat", "Heat-pump preheat", 1.4, 2, 3, 7, "manual-heatpump#0"),
        Task("dishwasher", "Dishwasher · Eco 50 °C", 0.5, 2, 0, 7, "manual-dishwasher#0"),
        Task("ev", "EV charge · eco mode", 3.6, 2, 0, 7, "manual-ev#1"),
        Task("laundry", "Washing machine · 40 °C", 0.8, 1, 0, 7, "manual-washer#0"),
    ]


def plan_to_dict(schedule: list[ScheduledTask], objective: Objective,
                 max_load_kw: float = 4.6,
                 avoid_hours: Sequence[int] = ()) -> dict[str, object]:
    validation = validate(schedule, max_load_kw, avoid_hours)
    return {
        "objective": objective,
        "schedule": [asdict(task) for task in schedule],
        "validation": validation,
        "total_cost_eur": round(sum(task.cost_eur for task in schedule), 2),
        "average_grid_stress": round(
            sum(task.grid_stress for task in schedule) / len(schedule)),
        "peak_load_kw": validation["peak_load_kw"],
    }


def create_demo_plan(objective: Objective = "balanced") -> dict[str, object]:
    schedule = optimize(demo_tasks(), objective)
    return plan_to_dict(schedule, objective)
