"""Entry point: python -m pipeline.run [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--full-refresh]"""
import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from . import extract, load, transform, validate
from .config import BACKFILL_START, LOOKBACK_DAYS, RATES_CSV, RUN_LOG_CSV, SITE_DATA_DIR

log = logging.getLogger("pipeline")


def resolve_window(existing: list[dict], start: str | None, end: str | None, full_refresh: bool) -> tuple[date, date]:
    end_d = date.fromisoformat(end) if end else date.today()
    if start:
        start_d = date.fromisoformat(start)
    elif full_refresh or not existing:
        start_d = date.fromisoformat(BACKFILL_START)
    else:
        last = max(date.fromisoformat(r["date"]) for r in existing)
        start_d = last - timedelta(days=LOOKBACK_DAYS)
    return start_d, end_d


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load Rupiah exchange rates into the dataset.")
    parser.add_argument("--start", help="first date to fetch (default: incremental)")
    parser.add_argument("--end", help="last date to fetch (default: today)")
    parser.add_argument("--full-refresh", action="store_true", help=f"reload everything from {BACKFILL_START}")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    started = datetime.now(timezone.utc)
    existing = [] if args.full_refresh else load.read_rates(RATES_CSV)
    start_d, end_d = resolve_window(existing, args.start, args.end, args.full_refresh)
    log.info("Fetching %s to %s", start_d, end_d)

    status, fetched, inserted, updated = "success", 0, 0, 0
    try:
        raw = extract.fetch_range(start_d, end_d)
        new_rows = transform.to_idr_rows(raw)
        fetched = len(new_rows)
        log.info("Fetched %d rows across %d trading days", fetched, len(raw))

        merged, inserted, updated = load.upsert(existing, new_rows)
        validate.assert_clean(merged)

        load.write_rates(RATES_CSV, merged)
        load.publish_site_data(SITE_DATA_DIR, merged)
        log.info("Dataset now has %d rows (%d inserted, %d updated)", len(merged), inserted, updated)
    except Exception as exc:  # noqa: BLE001 - recorded in the run log, then re-raised as exit code
        status = f"failed: {type(exc).__name__}"
        log.error("%s", exc)
    finally:
        load.append_run_log(RUN_LOG_CSV, {
            "run_at_utc": started.isoformat(timespec="seconds"),
            "window": f"{start_d}..{end_d}",
            "rows_fetched": fetched,
            "rows_inserted": inserted,
            "rows_updated": updated,
            "status": status,
        })
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
