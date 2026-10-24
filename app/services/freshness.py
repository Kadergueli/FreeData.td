"""How up to date is each data source?

A source is judged on the date of its newest *measurement* (not on when we last ran a
collection): a collector that runs every day but keeps fetching a frozen 2024 window would
otherwise look healthy. Each source has an expected maximum age, from how often it publishes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Days between today and the newest reference date that still counts as normal ("ok").
# Annual statistics are published with a lag of one to two years, hence ~3 years.
ANNUAL = 1100
SOURCE_MAX_AGE_DAYS: dict[str, int] = {
    "Open-Meteo Archive": 21,
    "Open-Meteo Agro-Climate": 21,
    "Open-Meteo Transport": 21,
    "NASA FIRMS VIIRS": 30,
    "NASA POWER": 100,
    "NASA POWER Agro": 100,
    "World Bank": ANNUAL,
    "UNESCO UIS": ANNUAL,
    "UNICEF Data": ANNUAL,
    "FAOSTAT": ANNUAL,
    "FAOSTAT / FreeData": ANNUAL,
}
DEFAULT_MAX_AGE_DAYS = 400  # unknown source: assume at most yearly updates

STATUS_ORDER = {"stale": 0, "late": 1, "ok": 2}


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def classify(age_days: int | None, max_age_days: int) -> str:
    """ok: within the normal age; late: up to twice that; stale: beyond (or no date)."""
    if age_days is None:
        return "stale"
    if age_days <= max_age_days:
        return "ok"
    if age_days <= 2 * max_age_days:
        return "late"
    return "stale"


def build_source_freshness(rows: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """rows: one dict per (sector, source) with sector, source, rows, latest_reference, last_published.
    Worst sources first, so the page opens on what needs attention."""
    result: list[dict[str, Any]] = []
    for row in rows:
        source = str(row.get("source") or "")
        latest = _to_date(row.get("latest_reference"))
        age = (today - latest).days if latest else None
        max_age = SOURCE_MAX_AGE_DAYS.get(source, DEFAULT_MAX_AGE_DAYS)
        published = row.get("last_published")
        result.append({
            "sector": row.get("sector"),
            "source": source,
            "rows": int(row.get("rows") or 0),
            "latest_reference": latest.isoformat() if latest else None,
            "last_published": str(published)[:10] if published else None,
            "age_days": age,
            "max_age_days": max_age,
            "status": classify(age, max_age),
        })
    result.sort(key=lambda r: (STATUS_ORDER[r["status"]], -(r["age_days"] or 0), r["sector"] or "", r["source"]))
    return result
