"""Load: upsert rows into the CSV dataset and publish JSON files for the dashboard."""
import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .config import CURRENCIES

FIELDS = ["date", "currency", "idr_per_unit"]


def read_rates(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [
            {"date": r["date"], "currency": r["currency"], "idr_per_unit": float(r["idr_per_unit"])}
            for r in csv.DictReader(f)
        ]


def upsert(existing: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """Merge on (date, currency). Returns (merged rows, inserted count, updated count)."""
    merged = {(r["date"], r["currency"]): r for r in existing}
    inserted = updated = 0
    for r in new:
        key = (r["date"], r["currency"])
        if key not in merged:
            inserted += 1
        elif merged[key]["idr_per_unit"] != r["idr_per_unit"]:
            updated += 1
        merged[key] = r
    rows = sorted(merged.values(), key=lambda r: (r["date"], CURRENCIES.index(r["currency"])))
    return rows, inserted, updated


def write_rates(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def append_run_log(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(entry))
        if new_file:
            w.writeheader()
        w.writerow(entry)


def summarize(rows: list[dict]) -> dict:
    """Latest rate, day-over-day change and 30-day volatility for each currency."""
    out = {}
    for ccy in CURRENCIES:
        series = [r for r in rows if r["currency"] == ccy]
        if len(series) < 2:
            continue
        latest, prev = series[-1], series[-2]
        changes = [b["idr_per_unit"] / a["idr_per_unit"] - 1 for a, b in zip(series, series[1:])][-30:]
        out[ccy] = {
            "date": latest["date"],
            "idr_per_unit": latest["idr_per_unit"],
            "change": round(latest["idr_per_unit"] - prev["idr_per_unit"], 4),
            "change_pct": round((latest["idr_per_unit"] / prev["idr_per_unit"] - 1) * 100, 3),
            "volatility_30d_pct": round(statistics.stdev(changes) * 100, 3) if len(changes) > 1 else None,
        }
    return out


def publish_site_data(site_dir: Path, rows: list[dict]) -> None:
    """Write compact JSON files that the static dashboard reads."""
    site_dir.mkdir(parents=True, exist_ok=True)
    dates = sorted({r["date"] for r in rows})
    index = {d: i for i, d in enumerate(dates)}
    series = {ccy: [None] * len(dates) for ccy in CURRENCIES}
    for r in rows:
        series[r["currency"]][index[r["date"]]] = r["idr_per_unit"]

    (site_dir / "rates.json").write_text(json.dumps({"dates": dates, "series": series}, separators=(",", ":")))
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "row_count": len(rows),
        "source": "European Central Bank reference rates via Frankfurter API",
        "currencies": summarize(rows),
    }
    (site_dir / "summary.json").write_text(json.dumps(summary, indent=2))
