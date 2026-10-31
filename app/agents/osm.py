"""OpenStreetMap feature counts per administrative region of Chad (Overpass API).

One small query per region (23 + N'Djamena), looked up by the region's ISO 3166-2 code, returning
only counts (`out count`): light for the public Overpass servers, and enough to answer "how many
hospitals / schools / aerodromes / main road segments are mapped in each region".

The numbers describe what contributors have MAPPED, not what exists: the indicator names say so.
Data: © OpenStreetMap contributors, ODbL 1.0."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# ISO 3166-2 code -> region name, spelled like the rest of the platform (no accents).
REGIONS: dict[str, str] = {
    "TD-BA": "Batha", "TD-BG": "Barh el Gazel", "TD-BO": "Borkou", "TD-CB": "Chari-Baguirmi",
    "TD-EE": "Ennedi Est", "TD-EO": "Ennedi Ouest", "TD-GR": "Guera", "TD-HL": "Hadjer-Lamis",
    "TD-KA": "Kanem", "TD-LC": "Lac", "TD-LO": "Logone Occidental", "TD-LR": "Logone Oriental",
    "TD-MA": "Mandoul", "TD-ME": "Mayo-Kebbi Est", "TD-MO": "Mayo-Kebbi Ouest", "TD-MC": "Moyen-Chari",
    "TD-ND": "N'Djamena", "TD-OD": "Ouaddai", "TD-SA": "Salamat", "TD-SI": "Sila",
    "TD-TA": "Tandjile", "TD-TI": "Tibesti", "TD-WF": "Wadi Fira",
}


@dataclass(frozen=True)
class OsmFeature:
    indicator: str
    unit: str
    selectors: tuple[str, ...]   # Overpass selectors WITHOUT the area filter; several = their union
    national: bool = False       # True: ONE query for the whole country (too slow to repeat per region)


HOSPITALS = OsmFeature("Mapped hospitals and clinics (OpenStreetMap)", "facilities",
                       ('nwr["amenity"="hospital"]', 'nwr["amenity"="clinic"]'))
SCHOOLS = OsmFeature("Mapped schools (OpenStreetMap)", "schools", ('nwr["amenity"="school"]',))
AERODROMES = OsmFeature("Mapped aerodromes (OpenStreetMap)", "aerodromes", ('nwr["aeroway"="aerodrome"]',), national=True)
# exact tag matches (no regular expression): much cheaper for the server than ["highway"~"..."]
MAIN_ROADS = OsmFeature("Mapped trunk and primary road segments (OpenStreetMap)", "segments",
                        ('way["highway"="trunk"]', 'way["highway"="primary"]'), national=True)


def build_query(iso_code: str, feature: OsmFeature, timeout: int = 120) -> str:
    """Overpass QL: the area (a region "TD-LC", or the whole country "TD"), then ONE `out count;` for
    the feature. One feature per query, so a slow feature cannot take the others down with it."""
    key = "ISO3166-2" if "-" in iso_code else "ISO3166-1"
    inner = "".join(f"{sel}(area.a);" for sel in feature.selectors)
    body = inner if len(feature.selectors) == 1 else f"({inner});"
    return f'[out:json][timeout:{timeout}];area["{key}"="{iso_code}"]->.a;{body}out count;'


def parse_counts(payload: Any, expected: int) -> list[int] | None:
    """Totals of the `count` elements of an Overpass answer, or None when the shape is wrong."""
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        return None
    counts: list[int] = []
    for element in payload["elements"]:
        if isinstance(element, dict) and element.get("type") == "count":
            try:
                counts.append(int((element.get("tags") or {}).get("total", 0)))
            except (TypeError, ValueError):
                return None
    return counts if len(counts) == expected else None


REQUEST_TIMEOUT = 150.0      # seconds, per request (the query itself asks Overpass for at most 120 s)
DEADLINE_SECONDS = 900.0     # the whole collection stops here, whatever happened
CONCURRENCY = 2              # the public Overpass servers give 2 slots per address
MAX_FIRST_FAILURES = 4       # this many failures before ANY success: the source is not answering, stop


async def _query(client: httpx.AsyncClient, query: str) -> tuple[Any, str]:
    """POST one query to each server in turn (one attempt each); returns (payload or None, reason)."""
    reason = "no detail"
    for url in OVERPASS_URLS:
        try:
            response = await client.post(url, data={"data": query},
                                         headers={"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedatatd.onrender.com)"})
            if response.status_code == 200:
                return response.json(), ""
            reason = f"HTTP {response.status_code}"
        except (httpx.RequestError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:100] or 'no detail'}"
    return None, reason


async def collect_osm_counts(features: list[OsmFeature], errors: list[str], pause: float = 1.0,
                             deadline_seconds: float = DEADLINE_SECONDS) -> list[dict[str, Any]]:
    """Counts of the given features for every region, as raw records (monthly snapshots).

    Bounded in time: two regions at once, a per-request timeout, a global deadline, and an early
    stop when the first requests all fail (a collection must never run for ever). A region whose
    answer is missing is skipped and counted in `errors`; a region where EVERY count is zero is
    also skipped (the ISO area was not found, which is not "nothing mapped"). Raises RuntimeError
    when nothing could be collected, so the run reports the source as failed."""
    today = datetime.now(UTC)
    started = time.monotonic()
    records: list[dict[str, Any]] = []
    failed: list[str] = []
    skipped: list[str] = []
    state: dict[str, Any] = {"ok": 0, "streak": 0, "stop": "", "reason": ""}
    gate = asyncio.Semaphore(CONCURRENCY)

    totals: dict[str, int] = {}
    jobs = [("TD", "national", f) for f in features if f.national]
    regional = [(iso, region, f) for iso, region in REGIONS.items() for f in features if not f.national]
    # Random order: when the public servers are too slow to finish every region, the next run
    # starts elsewhere, so the regions missed this time are the ones likely collected next time.
    random.shuffle(regional)
    jobs += regional

    async def one(client: httpx.AsyncClient, iso: str, region: str, feature: OsmFeature) -> None:
        async with gate:
            remaining = deadline_seconds - (time.monotonic() - started)
            if state["stop"] or remaining <= 0:
                state["stop"] = state["stop"] or "time limit reached"
                skipped.append(f"{region}/{feature.unit}")
                return
            try:
                payload, reason = await asyncio.wait_for(_query(client, build_query(iso, feature)), timeout=remaining)
            except asyncio.TimeoutError:
                state["stop"], payload, reason = "time limit reached", None, "time limit reached"
            counts = parse_counts(payload, 1) if payload is not None else None
            if counts is None:
                failed.append(f"{region}/{feature.unit}")
                state["reason"] = reason or "unexpected answer shape"
                state["streak"] += 1
                if state["ok"] == 0 and state["streak"] >= MAX_FIRST_FAILURES:
                    state["stop"] = "the source is not answering"
            else:
                state["ok"] += 1
                state["streak"] = 0
                totals[region] = totals.get(region, 0) + counts[0]
                if counts[0] > 0:
                    records.append({
                        "year": today.year, "month": today.month, "day": 1, "value": float(counts[0]),
                        "source": "OpenStreetMap", "indicator": feature.indicator, "unit": feature.unit,
                        "region": region, "url": "https://www.openstreetmap.org/copyright",
                    })
            await asyncio.sleep(pause)

    async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=15.0)) as client:
        await asyncio.gather(*(one(client, iso, region, feature) for iso, region, feature in jobs))
    empty = [region for region, total in totals.items() if total == 0 and region != "national"]

    missing = failed + skipped
    if missing:
        stopped = f"; stopped early: {state['stop']}" if state["stop"] else ""
        errors.append(f"OpenStreetMap: {len(missing)}/{len(jobs)} queries did not answer "
                      f"(last reason: {state['reason'] or 'none'}{stopped}); first: {', '.join(missing[:3])}")
    if empty:
        errors.append(f"OpenStreetMap: no mapped feature found for {len(empty)} region(s): {', '.join(empty[:5])}")
    if not records:
        raise RuntimeError(errors[0] if errors else "OpenStreetMap returned nothing")
    return records
