"""How often each sector is worth collecting.

Collecting a monthly statistic every day only re-downloads the same figures and wastes
the free-tier quota of the sources, so the automatic runs (scheduler, daily workflow)
only collect the sectors that are due. A run started by an administrator always collects
what was asked for."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

# Days between two automatic collections, matched to how often the sources really publish.
SECTOR_CADENCE_DAYS: dict[str, int] = {
    "environment": 1,   # weather, fires: new data every day
    "agriculture": 1,
    "markets": 7,       # market prices are reported weekly/monthly
    "transport": 7,
    "health": 30,       # national statistics: yearly, sometimes monthly
    "education": 30,
    "economy": 30,
    "energy": 30,
}
DEFAULT_CADENCE_DAYS = 1
# A daily run starts a few minutes after the previous one: without this margin a sector
# collected yesterday at 03:04 would be skipped at 03:01 today.
TOLERANCE = timedelta(hours=6)


def cadence_days(sector: str) -> int:
    return SECTOR_CADENCE_DAYS.get(sector, DEFAULT_CADENCE_DAYS)


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def last_success(runs: list[dict[str, Any]], sector: str) -> datetime | None:
    """Start time of the newest run in which the sector really collected something.

    A sector that raised, or that stored nothing while its sources reported errors, did
    not collect: it stays due so the next automatic run retries it."""
    best: datetime | None = None
    for run in runs:
        res = (run.get("results") or {}).get(sector)
        if not isinstance(res, dict) or res.get("error"):
            continue
        if res.get("errors") and not res.get("stored"):
            continue
        started = _parse(run.get("started_at"))
        if started and (best is None or started > best):
            best = started
    return best


def split_due(
    runs: list[dict[str, Any]], sectors: list[str], now: datetime | None = None,
) -> tuple[list[str], dict[str, str]]:
    """(sectors to collect now, {skipped sector: date it becomes due again})."""
    now = now or datetime.now(UTC)
    due: list[str] = []
    skipped: dict[str, str] = {}
    for sector in sectors:
        last = last_success(runs, sector)
        if last is None:
            due.append(sector)
            continue
        next_due = last + timedelta(days=cadence_days(sector)) - TOLERANCE
        if now >= next_due:
            due.append(sector)
        else:
            skipped[sector] = (last + timedelta(days=cadence_days(sector))).isoformat()
    return due, skipped
