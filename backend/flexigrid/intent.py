"""Mission understanding: natural language → typed, validated constraints.

This is where the generative model becomes load-bearing. The local LLM turns a
free-text household mission into a ``MissionSpec`` (typed tasks, windows,
objective, capacity cap). A deterministic sanitizer then clamps every value to
physically plausible ranges from the device catalog — the model proposes,
code disposes. When no model is reachable, a rule-based parser produces a
spec from the same text, so the pipeline never depends on model availability;
the response's ``mode`` field always states which path ran.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .core import Task
from .llm import LocalLLM
from .models import (DEFAULT_MAX_LOAD_KW, KNOWN_DEVICES, MissionSpec, Objective,
                     TaskSpec)

_INTENT_SYSTEM = (
    "You convert one household energy mission into machine-readable constraints. "
    "Devices you may use: ev (EV charger), dishwasher, laundry (washing machine), "
    "heat (heat-pump preheat). Hours are integers 0-23 on a single day; latest_end "
    "is exclusive (finish 'by 07:00' means latest_end=7). Include only devices the "
    "mission mentions. Typical values — ev: 3.6 kW for 2 h; dishwasher: 0.5 kW for "
    "2 h; laundry: 0.8 kW for 1 h; heat: 1.4 kW for 2 h. objective is 'cost' when "
    "the mission emphasises price, 'grid' when it emphasises supporting the grid or "
    "wind, else 'balanced'. avoid_hours lists whole hours the mission says to avoid. "
    "Never invent devices or deadlines that are not in the mission."
)

_HOUR_PATTERN = re.compile(r"(?:by|before|until|till)\s+(\d{1,2})(?::(\d{2}))?", re.IGNORECASE)
_AFTER_PATTERN = re.compile(r"(?:after|from|starting(?:\s+at)?)\s+(\d{1,2})(?::(\d{2}))?",
                            re.IGNORECASE)
_AVOID_PATTERN = re.compile(
    r"avoid[^.]*?(\d{1,2})(?::\d{2})?\s*(?:-|–|to|and)\s*(\d{1,2})(?::\d{2})?",
    re.IGNORECASE)

_DEVICE_HINTS: dict[str, tuple[str, ...]] = {
    "ev": ("ev", "car", "vehicle", "charge", "charger", "charging"),
    "dishwasher": ("dishwasher", "dishes", "dish washer"),
    "laundry": ("laundry", "washing machine", "washer", "wash"),
    "heat": ("heat", "preheat", "pre-heat", "warm", "heating", "°c"),
}


def _mentions(text: str, hints: tuple[str, ...]) -> bool:
    """Word-boundary hint matching ('dishwasher' must not trigger 'washer')."""
    return any(re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", text)
               for hint in hints)


@dataclass
class IntentResult:
    spec: MissionSpec
    mode: str                      # "llm" | "rules"
    notes: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)


def _ceil_hour(hour: int, minutes: int | None) -> int:
    return min(hour + (1 if minutes else 0), 24)


def rule_based_spec(mission: str) -> MissionSpec:
    """Deterministic fallback parser (also the intent-extraction ablation)."""
    text = mission.lower()
    deadline = 24
    match = _HOUR_PATTERN.search(text)
    if match:
        deadline = _ceil_hour(int(match.group(1)),
                              int(match.group(2)) if match.group(2) else 0)
        deadline = max(1, min(deadline, 24))
    earliest = 0
    after = _AFTER_PATTERN.search(text)
    if after:
        earliest = max(0, min(int(after.group(1)), 23))

    avoid: list[int] = []
    avoid_match = _AVOID_PATTERN.search(text)
    if avoid_match:
        start, end = int(avoid_match.group(1)), int(avoid_match.group(2))
        if 0 <= start < end <= 24:
            avoid = list(range(start, end))

    tasks: list[TaskSpec] = []
    for device, hints in _DEVICE_HINTS.items():
        if _mentions(text, hints):
            catalog = KNOWN_DEVICES[device]
            duration = int(catalog["duration_hours"])
            latest = deadline
            start_floor = earliest
            if device == "heat" and deadline <= 12:
                # Pre-heat is most useful just before the deadline (comfort policy).
                start_floor = max(earliest, deadline - 4)
            if latest - start_floor < duration:
                start_floor = max(0, latest - duration)
            tasks.append(TaskSpec(
                task_id=device,  # type: ignore[arg-type]
                power_kw=float(catalog["power_kw"]),
                duration_hours=duration,
                earliest_start=start_floor,
                latest_end=latest,
            ))
    if not tasks:  # mission mentioned no known device — schedule the full set
        for device, catalog in KNOWN_DEVICES.items():
            duration = int(catalog["duration_hours"])
            start_floor = earliest if device != "heat" else max(earliest, deadline - 4)
            if deadline - start_floor < duration:
                start_floor = max(0, deadline - duration)
            tasks.append(TaskSpec(
                task_id=device,  # type: ignore[arg-type]
                power_kw=float(catalog["power_kw"]),
                duration_hours=duration,
                earliest_start=start_floor,
                latest_end=deadline,
            ))

    objective: Objective = "balanced"
    if any(word in text for word in ("cheap", "cost", "price", "money", "€", "eur")):
        objective = "cost"
    if any(word in text for word in ("grid", "wind", "renewable", "support", "peak")):
        objective = "grid" if objective == "balanced" else objective

    cap = DEFAULT_MAX_LOAD_KW
    cap_match = re.search(r"(\d(?:[.,]\d)?)\s*kw", text)
    if cap_match:
        parsed_cap = float(cap_match.group(1).replace(",", "."))
        if 2.0 <= parsed_cap <= 9.2:
            cap = parsed_cap

    return MissionSpec(tasks=tasks, objective=objective, max_load_kw=cap,
                       avoid_hours=avoid, notes="rule-based extraction")


def sanitize(spec: MissionSpec) -> tuple[MissionSpec, list[str]]:
    """Clamp model output to physical plausibility. The model proposes, code disposes."""
    adjustments: list[str] = []
    tasks: list[TaskSpec] = []
    seen: set[str] = set()
    for task in spec.tasks:
        if task.task_id in seen:
            adjustments.append(f"dropped duplicate task '{task.task_id}'")
            continue
        seen.add(task.task_id)
        catalog = KNOWN_DEVICES[task.task_id]
        low, high = catalog["power_range"]  # type: ignore[misc]
        power = task.power_kw
        if not low <= power <= high:
            power = float(catalog["power_kw"])
            adjustments.append(
                f"{task.task_id}: power {task.power_kw} kW outside plausible "
                f"range [{low}, {high}] — reset to {power} kW")
        earliest = max(0, min(task.earliest_start, 23))
        latest = max(1, min(task.latest_end, 24))
        duration = max(1, min(task.duration_hours, 6))
        if latest - earliest < duration:
            new_earliest = max(0, latest - duration)
            adjustments.append(
                f"{task.task_id}: window [{earliest}, {latest}) shorter than "
                f"{duration} h — earliest_start moved to {new_earliest}")
            earliest = new_earliest
        tasks.append(TaskSpec(task_id=task.task_id, power_kw=power,
                              duration_hours=duration, earliest_start=earliest,
                              latest_end=latest))
    if not tasks:
        raise ValueError("Mission produced no usable tasks")
    avoid = sorted({hour % 24 for hour in spec.avoid_hours})
    if avoid != sorted(spec.avoid_hours):
        adjustments.append("avoid_hours normalized into 0-23")
    return (MissionSpec(tasks=tasks, objective=spec.objective,
                        max_load_kw=spec.max_load_kw, avoid_hours=avoid,
                        notes=spec.notes),
            adjustments)


def extract_intent(mission: str, llm: LocalLLM | None = None,
                   use_llm: bool = True) -> IntentResult:
    notes: list[str] = []
    if use_llm and llm is not None and llm.available():
        raw_spec, llm_notes = llm.structured(
            MissionSpec, _INTENT_SYSTEM, f"Mission: {mission}")
        notes.extend(llm_notes)
        if raw_spec is not None:
            try:
                spec, adjustments = sanitize(raw_spec)
                return IntentResult(spec=spec, mode="llm", notes=notes,
                                    adjustments=adjustments)
            except ValueError as error:
                notes.append(f"llm spec rejected: {error}")
        notes.append("falling back to rule-based extraction")
    spec, adjustments = sanitize(rule_based_spec(mission))
    return IntentResult(spec=spec, mode="rules", notes=notes,
                        adjustments=adjustments)


def spec_to_tasks(spec: MissionSpec) -> list[Task]:
    tasks = []
    for item in spec.tasks:
        catalog = KNOWN_DEVICES[item.task_id]
        tasks.append(Task(
            task_id=item.task_id,
            name=str(catalog["name"]),
            power_kw=item.power_kw,
            duration_hours=item.duration_hours,
            earliest_start=item.earliest_start,
            latest_end=item.latest_end,
            source_id=str(catalog["source_id"]),
        ))
    return tasks
