"""Fetch raw Elia records for a reproducible research snapshot.

Usage from backend/: python scripts/fetch_elia_snapshot.py
The output intentionally preserves raw API records and includes retrieval time.
"""

from __future__ import annotations

import json
from pathlib import Path

from flexigrid.elia_client import EliaClient, SUPPORTED_DATASETS


def main() -> None:
    output = Path("data/elia_live_snapshot.json")
    client = EliaClient(timeout_seconds=15)
    payload = {
        "mode": "live-snapshot",
        "datasets": {dataset: client.fetch_records(dataset, limit=100) for dataset in sorted(SUPPORTED_DATASETS)},
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
