"""Elia Open Data adapter.

Live mode fetches raw quarter-hour records from the official Opendatasoft API
and derives the hourly stress signal with ``derive.py``. When the network or
the API is unavailable — or live mode is off, the default for reproducible
examinations — the clearly labelled frozen fixture is served instead. The
``mode`` and ``provenance`` fields always say which one the caller received.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .derive import DerivationError, derive_stress

ELIA_API = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets"
SUPPORTED_DATASETS = {"ods002", "ods086", "ods201"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_PATH = DATA_DIR / "elia_demo_snapshot.json"


class EliaClient:
    def __init__(self, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_records(self, dataset_id: str, limit: int = 100) -> dict[str, Any]:
        if dataset_id not in SUPPORTED_DATASETS:
            raise ValueError(f"Unsupported Elia dataset: {dataset_id}")
        response = httpx.get(
            f"{ELIA_API}/{dataset_id}/records",
            params={"limit": min(max(limit, 1), 100), "order_by": "datetime desc"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "dataset_id": dataset_id,
            "source": "Elia Open Data API",
            "fetched_at": datetime.now(UTC).isoformat(),
            "records": payload.get("results", []),
        }

    def _frozen(self) -> dict[str, Any]:
        with SNAPSHOT_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    def snapshot(self, use_live: bool = False) -> dict[str, Any]:
        """Hourly tariff + stress with provenance. Never raises on live failure."""
        if use_live:
            try:
                load = self.fetch_records("ods002", 96)
                wind = self.fetch_records("ods086", 96)
                derived = derive_stress(load["records"], wind["records"])
                frozen = self._frozen()
                return {
                    "mode": "live-derived",
                    "provenance": {
                        "stress": "derived from Elia ods002 + ods086 records",
                        "fetched_at": load["fetched_at"],
                        "tariff": "frozen retail-tariff fixture (retail prices are "
                                  "not published by Elia; see tariff-dynamic corpus doc)",
                    },
                    "normalized_hourly": {
                        "tariff_eur_per_kwh":
                            frozen["normalized_hourly"]["tariff_eur_per_kwh"],
                        "derived_grid_stress_0_100": derived["stress_0_100"],
                    },
                    "derivation": derived,
                }
            except (httpx.HTTPError, DerivationError, ValueError, KeyError) as error:
                fallback = self._frozen()
                fallback["live_error"] = f"{type(error).__name__}: {error}"
                return fallback
        return self._frozen()

    def series(self, use_live: bool = False) -> tuple[list[float], list[int], str]:
        """Convenience: (tariff, stress, mode) for the planner."""
        snapshot = self.snapshot(use_live=use_live)
        hourly = snapshot["normalized_hourly"]
        return (
            list(hourly["tariff_eur_per_kwh"]),
            list(hourly["derived_grid_stress_0_100"]),
            snapshot.get("mode", "unknown"),
        )
