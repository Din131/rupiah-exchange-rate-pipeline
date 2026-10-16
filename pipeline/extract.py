"""Extract: download ECB reference rates (base EUR) from the Frankfurter API."""
import json
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from .config import API_BASE, CURRENCIES

USER_AGENT = "rupiah-exchange-rate-pipeline (+https://github.com/Din131/rupiah-exchange-rate-pipeline)"


def _get_json(url: str, retries: int = 3, backoff: float = 5.0) -> dict:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_error}")


def _symbols() -> str:
    # IDR is always needed; EUR is the base and is not requested.
    return ",".join(sorted({"IDR", *(c for c in CURRENCIES if c != "EUR")}))


def fetch_range(start: date, end: date, chunk_days: int = 365) -> dict:
    """Return {"YYYY-MM-DD": {"IDR": .., "USD": .., ...}} with rates per 1 EUR.

    Long ranges are split into yearly chunks to keep each response small.
    """
    rates: dict = {}
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        url = f"{API_BASE}/{cursor.isoformat()}..{chunk_end.isoformat()}?symbols={_symbols()}"
        payload = _get_json(url)
        rates.update(payload.get("rates", {}))
        cursor = chunk_end + timedelta(days=1)
    return rates
