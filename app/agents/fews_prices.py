"""Market prices from the FEWS NET Data Warehouse (public API, no key).

    GET https://fdw.fews.net/api/marketpricefacts/?country_code=TD&format=json&start_date=...

Documented at https://help.fews.net/fdw/fews-net-api . The documentation lists the filters but
not the exact JSON field names, so parsing accepts the usual spellings and the module is
exercised against a real response with `python -m app.cli probe-prices` before trusting it.
Terms: reuse and redistribution are allowed with attribution (FEWS NET Data and Information
Use and Attribution Policy); the source name, licence and notes carry that attribution.
"""
from __future__ import annotations

from datetime import date
from typing import Any

FEWS_URL = "https://fdw.fews.net/api/marketpricefacts/"
SOURCE_LABEL = "FEWS NET"
LICENSE = "FEWS NET terms (attribution)"
ATTRIBUTION = "Famine Early Warning Systems Network (FEWS NET), fews.net. Reuse requires this attribution."


def _text(value: Any) -> str | None:
    """A string from a plain value or from a nested object like {"name": "Abéché"}."""
    if isinstance(value, dict):
        for key in ("name", "label", "title", "code"):
            if value.get(key):
                return str(value[key]).strip() or None
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    return None


def extract_items(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """(records, next page URL) from a bare list or a paginated {"results": [...], "next": ...}."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)], None
    if isinstance(payload, dict):
        for key in ("results", "data", "items"):
            if isinstance(payload.get(key), list):
                nxt = payload.get("next")
                return [x for x in payload[key] if isinstance(x, dict)], nxt if isinstance(nxt, str) and nxt else None
    raise ValueError("unexpected FEWS NET response shape (not a list or a paginated object)")


def parse_record(item: dict[str, Any]) -> dict[str, Any] | None:
    """One raw FEWS NET row -> the dict MarketsAgent.normalize understands, or None if unusable."""
    raw_value = _pick(item, "value", "price", "amount")
    raw_date = _text(_pick(item, "period_date", "date", "period", "start_date"))
    product = _text(_pick(item, "product", "product_name", "commodity"))
    if raw_value is None or not raw_date or not product:
        return None
    try:
        value = float(raw_value)
        when = date.fromisoformat(raw_date[:10])
    except (TypeError, ValueError):
        return None
    if value <= 0:                        # a price is never zero or negative: a missing value, not a price
        return None

    market = _text(_pick(item, "market", "market_name", "location"))
    admin = _text(_pick(item, "admin_1", "admin1", "region", "province"))
    price_type = (_text(_pick(item, "price_type", "pricetype")) or "retail").lower()
    unit = _text(_pick(item, "unit", "unit_of_measure")) or "kg"
    currency = _text(_pick(item, "currency", "currency_code")) or "XOF"

    indicator = f"{product} price ({price_type})"
    if admin and market and market.lower() != admin.lower():
        indicator = f"{indicator} - {market}"
    return {
        "year": when.year, "month": when.month, "day": when.day,
        "value": value,
        "indicator": indicator[:100],
        "unit": f"{currency}/{unit}"[:30],
        "region": (admin or market or "national")[:50],
        "source": SOURCE_LABEL,
        "url": FEWS_URL,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
    }
