"""Central configuration for the Rupiah exchange-rate pipeline."""
from pathlib import Path

# Frankfurter serves the European Central Bank's daily reference rates (base EUR).
API_BASE = "https://api.frankfurter.dev/v1"

# Currencies tracked against the Rupiah. EUR is the ECB base, so it needs no lookup.
CURRENCIES = ["USD", "SGD", "EUR", "JPY", "CNY", "MYR"]

# First date loaded on an empty dataset (full backfill).
BACKFILL_START = "2015-01-01"

# On incremental runs, re-read this many days before the last stored date so that
# late corrections published by the source are picked up (upsert, not append).
LOOKBACK_DAYS = 7

# A day-over-day move larger than this is treated as a data error, not a market move.
MAX_DAILY_CHANGE = 0.10

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RATES_CSV = DATA_DIR / "idr_rates.csv"
RUN_LOG_CSV = DATA_DIR / "run_log.csv"
SITE_DATA_DIR = ROOT / "docs" / "data"
