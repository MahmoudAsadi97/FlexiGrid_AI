from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Objective = Literal["balanced", "cost", "grid"]

TARIFF = [
    0.22, 0.18, 0.16, 0.15, 0.14, 0.15, 0.19, 0.27, 0.31, 0.29, 0.25, 0.23,
    0.21, 0.20, 0.22, 0.28, 0.37, 0.46, 0.42, 0.34, 0.28, 0.24, 0.21, 0.19,
]

GRID_STRESS = [
    48, 42, 38, 34, 31, 33, 45, 59, 71, 76, 68, 55,
    42, 35, 29, 32, 51, 78, 91, 86, 70, 58, 52, 47,
]


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


def _slot_score(task: Task, start: int, objective: Objective) -> float:
    cost_weight = {"cost": 0.84, "grid": 0.18, "balanced": 0.56}[objective]
    max_price = max(TARIFF)
    score = 0.0
    for hour in range(start, start + task.duration_hours):
        score += cost_weight * (TARIFF[hour] / max_price)
        score += (1 - cost_weight) * (GRID_STRESS[hour] / 100)
    return score


def _metrics(task: Task, start: int) -> tuple[float, int]:
    hours = range(start, start + task.duration_hours)
    cost = sum(task.power_kw * TARIFF[hour] for hour in hours)
    stress = round(sum(GRID_STRESS[hour] for hour in hours) / task.duration_hours)
    return round(cost, 2), stress


def optimize(tasks: list[Task], objective: Objective, max_load_kw: float = 4.6) -> list[ScheduledTask]:
    """Exhaustive constrained search; the LLM never decides feasibility."""
    load = [0.0] * 24
    best_score = float("inf")
    best_starts: dict[str, int] | None = None
    ordered = sorted(
        tasks,
        key=lambda task: (
            task.latest_end - task.earliest_start - task.duration_hours,
            -task.power_kw,
            task.task_id,
        ),
    )

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
            range(task.earliest_start, task.latest_end - task.duration_hours + 1),
            key=lambda start: (_slot_score(task, start, objective), start),
        )
        for start in candidates:
            hours = range(start, start + task.duration_hours)
            if not all(load[hour] + task.power_kw <= max_load_kw + 1e-9 for hour in hours):
                continue
            for hour in hours:
                load[hour] += task.power_kw
            starts[task.task_id] = start
            search(index + 1, score + _slot_score(task, start, objective), starts)
            del starts[task.task_id]
            for hour in hours:
                load[hour] -= task.power_kw

    search(0, 0.0, {})
    if best_starts is None:
        raise ValueError("No feasible schedule for the supplied constraints")

    scheduled: list[ScheduledTask] = []
    for task in ordered:
        start = best_starts[task.task_id]
        cost, stress = _metrics(task, start)
        scheduled.append(
            ScheduledTask(
                **asdict(task),
                start=start,
                end=start + task.duration_hours,
                cost_eur=cost,
                grid_stress=stress,
            )
        )
    return scheduled


def validate(schedule: list[ScheduledTask], max_load_kw: float = 4.6) -> dict[str, object]:
    load = [0.0] * 24
    within_windows = True
    for task in schedule:
        within_windows = within_windows and task.start >= task.earliest_start and task.end <= task.latest_end
        for hour in range(task.start, task.end):
            load[hour] += task.power_kw
    below_capacity = all(value <= max_load_kw + 1e-9 for value in load)
    return {
        "valid": within_windows and below_capacity,
        "within_windows": within_windows,
        "below_capacity": below_capacity,
        "peak_load_kw": round(max(load), 2),
        "hourly_load_kw": [round(value, 2) for value in load],
    }


def demo_tasks() -> list[Task]:
    return [
        Task("heat", "Heat-pump preheat", 1.4, 2, 3, 7, "comfort-home"),
        Task("dishwasher", "Dishwasher · Eco", 0.5, 2, 0, 7, "manual-dw-11"),
        Task("ev", "EV charge · 7.2 kWh", 3.6, 2, 0, 7, "manual-ev-04"),
        Task("laundry", "Laundry", 0.8, 1, 0, 7, "grid-capacity"),
    ]


def create_demo_plan(objective: Objective = "balanced") -> dict[str, object]:
    schedule = optimize(demo_tasks(), objective)
    validation = validate(schedule)
    return {
        "objective": objective,
        "schedule": [asdict(task) for task in schedule],
        "validation": validation,
        "total_cost_eur": round(sum(task.cost_eur for task in schedule), 2),
        "average_grid_stress": round(sum(task.grid_stress for task in schedule) / len(schedule)),
    }
