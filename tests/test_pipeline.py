"""Offline tests: no network access is needed (the API call is replaced by a fixture)."""
import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from pipeline import load, run, transform, validate

# Rates per 1 EUR, shaped like the Frankfurter API response.
RAW = {
    "2026-10-01": {"IDR": 19000.0, "USD": 1.16, "SGD": 1.50, "JPY": 172.0, "CNY": 8.30, "MYR": 4.90},
    "2026-10-02": {"IDR": 19100.0, "USD": 1.17, "SGD": 1.51, "JPY": 173.0, "CNY": 8.31, "MYR": 4.91},
    "2026-10-05": {"IDR": 19050.0, "USD": 1.165, "SGD": 1.505, "JPY": 172.5, "CNY": 8.305, "MYR": 4.905},
}


class TransformTest(unittest.TestCase):
    def test_cross_rate(self):
        rows = transform.to_idr_rows(RAW)
        usd = next(r for r in rows if r["date"] == "2026-10-01" and r["currency"] == "USD")
        self.assertAlmostEqual(usd["idr_per_unit"], 19000 / 1.16, places=3)

    def test_eur_is_direct_quote(self):
        rows = transform.to_idr_rows(RAW)
        eur = next(r for r in rows if r["date"] == "2026-10-01" and r["currency"] == "EUR")
        self.assertEqual(eur["idr_per_unit"], 19000.0)

    def test_days_without_idr_are_skipped(self):
        rows = transform.to_idr_rows({"2026-10-01": {"USD": 1.16}})
        self.assertEqual(rows, [])


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.rows = transform.to_idr_rows(RAW)

    def test_clean_data_passes(self):
        self.assertEqual(validate.check(self.rows, today=date(2026, 10, 16)), [])

    def test_duplicates_are_caught(self):
        issues = validate.check(self.rows + [self.rows[0]], today=date(2026, 10, 16))
        self.assertTrue(any("duplicate" in i for i in issues))

    def test_spike_is_caught(self):
        bad = [dict(r) for r in self.rows]
        bad[-1]["idr_per_unit"] *= 1.5
        issues = validate.check(bad, today=date(2026, 10, 16))
        self.assertTrue(any("moved" in i for i in issues))

    def test_missing_currency_is_caught(self):
        partial = [r for r in self.rows if not (r["date"] == "2026-10-02" and r["currency"] == "MYR")]
        issues = validate.check(partial, today=date(2026, 10, 16))
        self.assertTrue(any("missing" in i for i in issues))

    def test_future_date_is_caught(self):
        issues = validate.check(self.rows, today=date(2026, 10, 1))
        self.assertTrue(any("future" in i for i in issues))


class LoadTest(unittest.TestCase):
    def test_upsert_counts_and_overwrites(self):
        old = [{"date": "2026-10-01", "currency": "USD", "idr_per_unit": 1.0}]
        new = [{"date": "2026-10-01", "currency": "USD", "idr_per_unit": 2.0},
               {"date": "2026-10-02", "currency": "USD", "idr_per_unit": 3.0}]
        merged, inserted, updated = load.upsert(old, new)
        self.assertEqual((inserted, updated), (1, 1))
        self.assertEqual(merged[0]["idr_per_unit"], 2.0)


class EndToEndTest(unittest.TestCase):
    def test_run_writes_dataset_site_data_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with mock.patch.object(run, "RATES_CSV", tmp / "rates.csv"), \
                 mock.patch.object(run, "RUN_LOG_CSV", tmp / "run_log.csv"), \
                 mock.patch.object(run, "SITE_DATA_DIR", tmp / "site"), \
                 mock.patch.object(run.extract, "fetch_range", return_value=RAW):
                code = run.main(["--start", "2026-10-01", "--end", "2026-10-05"])

            self.assertEqual(code, 0)
            with (tmp / "rates.csv").open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 18)  # 3 days x 6 currencies
            summary = json.loads((tmp / "site" / "summary.json").read_text())
            self.assertEqual(summary["last_date"], "2026-10-05")
            self.assertIn("USD", summary["currencies"])
            with (tmp / "run_log.csv").open() as f:
                self.assertEqual(list(csv.DictReader(f))[-1]["status"], "success")

    def test_failed_validation_keeps_old_data(self):
        bad = {d: dict(q) for d, q in RAW.items()}
        bad["2026-10-05"]["IDR"] = 40000.0  # impossible jump
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with mock.patch.object(run, "RATES_CSV", tmp / "rates.csv"), \
                 mock.patch.object(run, "RUN_LOG_CSV", tmp / "run_log.csv"), \
                 mock.patch.object(run, "SITE_DATA_DIR", tmp / "site"), \
                 mock.patch.object(run.extract, "fetch_range", return_value=bad):
                code = run.main(["--start", "2026-10-01", "--end", "2026-10-05"])
            self.assertEqual(code, 1)
            self.assertFalse((tmp / "rates.csv").exists())


if __name__ == "__main__":
    unittest.main()
