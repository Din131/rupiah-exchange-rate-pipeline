"""Validate: data-quality checks run before anything is written."""
from collections import defaultdict
from datetime import date

from .config import CURRENCIES, MAX_DAILY_CHANGE


class ValidationError(Exception):
    """Raised when the dataset fails a data-quality check."""


def check(rows: list[dict], today: date | None = None) -> list[str]:
    """Return a list of human-readable issues; an empty list means the data is clean."""
    today = today or date.today()
    issues: list[str] = []

    if not rows:
        return ["dataset is empty"]

    seen = set()
    by_currency = defaultdict(list)
    dates_per_day = defaultdict(set)
    for r in rows:
        key = (r["date"], r["currency"])
        if key in seen:
            issues.append(f"duplicate row {key}")
        seen.add(key)
        if r["idr_per_unit"] is None or r["idr_per_unit"] <= 0:
            issues.append(f"non-positive rate {key}: {r['idr_per_unit']}")
        if date.fromisoformat(r["date"]) > today:
            issues.append(f"future date {key}")
        by_currency[r["currency"]].append(r)
        dates_per_day[r["date"]].add(r["currency"])

    for day, ccys in dates_per_day.items():
        missing = set(CURRENCIES) - ccys
        if missing:
            issues.append(f"{day} is missing {sorted(missing)}")

    for ccy, series in by_currency.items():
        series.sort(key=lambda r: r["date"])
        for prev, cur in zip(series, series[1:]):
            change = abs(cur["idr_per_unit"] / prev["idr_per_unit"] - 1)
            if change > MAX_DAILY_CHANGE:
                issues.append(
                    f"{ccy} moved {change:.1%} from {prev['date']} to {cur['date']} "
                    f"(limit {MAX_DAILY_CHANGE:.0%})"
                )
    return issues


def assert_clean(rows: list[dict], today: date | None = None) -> None:
    issues = check(rows, today)
    if issues:
        shown = "\n  - ".join(issues[:20])
        more = f"\n  ... and {len(issues) - 20} more" if len(issues) > 20 else ""
        raise ValidationError(f"{len(issues)} data-quality issue(s):\n  - {shown}{more}")
