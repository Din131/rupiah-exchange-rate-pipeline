"""Transform: turn EUR-based reference rates into Rupiah per one unit of each currency."""
from .config import CURRENCIES


def to_idr_rows(raw: dict) -> list[dict]:
    """Convert {date: {ccy: rate_per_EUR}} into long rows of IDR per 1 unit.

    Cross rate: IDR per 1 X = (IDR per EUR) / (X per EUR). For EUR itself the
    ECB quote is already IDR per EUR. Dates without an IDR quote are skipped.
    """
    rows = []
    for day in sorted(raw):
        quotes = raw[day]
        idr_per_eur = quotes.get("IDR")
        if not idr_per_eur:
            continue
        for ccy in CURRENCIES:
            per_eur = 1.0 if ccy == "EUR" else quotes.get(ccy)
            if not per_eur:
                continue
            rows.append({
                "date": day,
                "currency": ccy,
                "idr_per_unit": round(idr_per_eur / per_eur, 4),
            })
    return rows
