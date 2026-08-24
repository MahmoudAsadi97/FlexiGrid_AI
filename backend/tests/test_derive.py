"""Grid-stress derivation pipeline on schema-accurate raw records."""

import json
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401

from flexigrid.derive import DerivationError, derive_stress, hourly_means

DATA = Path(__file__).resolve().parent.parent / "data"


def _fixture() -> dict:
    return json.loads((DATA / "elia_raw_fixture.json").read_text())


class DeriveTests(unittest.TestCase):
    def test_fixture_is_labelled_synthetic(self):
        fixture = _fixture()
        self.assertEqual(fixture["mode"], "synthetic-raw-records-fixture")
        self.assertIn("not Elia data", fixture["warning"])

    def test_derivation_produces_bounded_24h_series(self):
        fixture = _fixture()
        result = derive_stress(fixture["datasets"]["ods002"]["records"],
                               fixture["datasets"]["ods086"]["records"])
        stress = result["stress_0_100"]
        self.assertEqual(len(stress), 24)
        self.assertTrue(all(0 <= value <= 100 for value in stress))
        self.assertEqual(min(stress), 0)
        self.assertEqual(max(stress), 100)

    def test_high_wind_lowers_stress(self):
        load = [{"datetime": f"2026-08-24T{hour:02d}:00:00+00:00",
                 "dayaheadforecast": 10000.0} for hour in range(24)]
        calm = [{"datetime": f"2026-08-24T{hour:02d}:00:00+00:00",
                 "dayaheadforecast": 100.0} for hour in range(24)]
        windy_at_night = [
            {"datetime": f"2026-08-24T{hour:02d}:00:00+00:00",
             "dayaheadforecast": 4000.0 if hour < 6 else 100.0}
            for hour in range(24)]
        flat = derive_stress(load, calm)["stress_0_100"]
        shaped = derive_stress(load, windy_at_night)["stress_0_100"]
        self.assertLess(sum(shaped[:6]), sum(shaped[6:12]))
        self.assertEqual(len(set(flat)), 1)  # constant inputs → flat stress

    def test_hourly_means_buckets_quarter_hours(self):
        records = [{"datetime": f"2026-08-24T03:{minute:02d}:00+00:00",
                    "dayaheadforecast": value}
                   for minute, value in ((0, 10.0), (15, 20.0), (30, 30.0),
                                         (45, 40.0))]
        means = hourly_means(records, "dayaheadforecast")
        self.assertEqual(means[3], 25.0)
        self.assertIsNone(means[4])

    def test_sparse_records_raise(self):
        few = [{"datetime": "2026-08-24T01:00:00+00:00",
                "dayaheadforecast": 5000.0}]
        with self.assertRaises(DerivationError):
            derive_stress(few, few)

    def test_nested_fields_shape_is_accepted(self):
        nested = [{"fields": {"datetime": f"2026-08-24T{hour:02d}:00:00+00:00",
                              "dayaheadforecast": 8000.0 + hour}}
                  for hour in range(24)]
        result = derive_stress(nested, nested)
        self.assertEqual(len(result["stress_0_100"]), 24)


if __name__ == "__main__":
    unittest.main()
