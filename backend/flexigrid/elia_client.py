from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ELIA_API = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets"
SUPPORTED_DATASETS = {"ods002", "ods086", "ods201"}
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "elia_demo_snapshot.json"


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

    def snapshot(self, use_live: bool = False) -> dict[str, Any]:
        if use_live:
            try:
                return {
                    "mode": "live",
                    "datasets": {dataset: self.fetch_records(dataset, 96) for dataset in sorted(SUPPORTED_DATASETS)},
                }
            except (httpx.HTTPError, ValueError):
                pass
        with SNAPSHOT_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
