"""Derive the hourly grid-stress signal from raw Elia records.

Implements the methodology documented in ``corpus/pipeline-stress.md``:

1. Bucket quarter-hour day-ahead forecasts into hourly means.
2. Min-max normalize hourly load (ods002) and wind (ods086) over the day.
3. stress = normalized_load − 0.5 · normalized_wind, rescaled to 0–100.

The function is pure and fully unit-tested against a schema-accurate fixture,
so the exact same code runs on a live snapshot fetched with
``scripts/fetch_elia_snapshot.py`` on a networked machine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

WIND_WEIGHT = 0.5


class DerivationError(ValueError):
    """Raised when the raw records cannot support a 24-hour derivation."""


def _pick(record: dict[str, Any], *candidates: str) -> float | None:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
    for name in candidates:
        value = fields.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _hour_of(record: dict[str, Any]) -> int | None:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
    stamp = fields.get("datetime") or fields.get("date")
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).hour
    except ValueError:
        return None


def hourly_means(records: Iterable[dict[str, Any]], *value_fields: str) -> list[float | None]:
    """Average quarter-hour records into 24 hourly buckets."""
    sums = [0.0] * 24
    counts = [0] * 24
    for record in records:
        hour = _hour_of(record)
        value = _pick(record, *value_fields)
        if hour is None or value is None:
            continue
        sums[hour] += value
        counts[hour] += 1
    return [sums[h] / counts[h] if counts[h] else None for h in range(24)]


def _fill_gaps(series: list[float | None]) -> list[float]:
    """Fill missing hours by nearest-neighbour interpolation."""
    known = [(index, value) for index, value in enumerate(series) if value is not None]
    if len(known) < 12:
        raise DerivationError(
            f"Only {len(known)} of 24 hours present in the records")
    filled: list[float] = []
    for index in range(24):
        if series[index] is not None:
            filled.append(float(series[index]))
        else:
            nearest = min(known, key=lambda item: (abs(item[0] - index), item[0]))
            filled.append(float(nearest[1]))
    return filled


def _min_max(series: list[float]) -> list[float]:
    low, high = min(series), max(series)
    if high - low < 1e-9:
        return [0.5] * len(series)
    return [(value - low) / (high - low) for value in series]


def derive_stress(load_records: Iterable[dict[str, Any]],
                  wind_records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return the 0–100 hourly stress series plus intermediate signals."""
    load_hourly = _fill_gaps(hourly_means(
        load_records,
        "dayaheadforecast", "day_ahead_forecast", "mostrecentforecast", "totalload",
    ))
    wind_hourly = _fill_gaps(hourly_means(
        wind_records,
        "dayaheadforecast", "day_ahead_forecast", "mostrecentforecast", "realtime",
    ))
    load_norm = _min_max(load_hourly)
    wind_norm = _min_max(wind_hourly)
    raw = [load_norm[h] - WIND_WEIGHT * wind_norm[h] for h in range(24)]
    raw_norm = _min_max(raw)
    stress = [round(value * 100) for value in raw_norm]
    return {
        "stress_0_100": stress,
        "load_mw_hourly": [round(value, 1) for value in load_hourly],
        "wind_mw_hourly": [round(value, 1) for value in wind_hourly],
        "wind_weight": WIND_WEIGHT,
        "method": "minmax(load) - 0.5*minmax(wind), rescaled to 0-100",
    }
