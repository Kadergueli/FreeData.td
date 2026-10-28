"""OpenStreetMap feature counts per administrative region of Chad (Overpass API).

One small query per region (23 + N'Djamena), looked up by the region's ISO 3166-2 code, returning
only counts (`out count`): light for the public Overpass servers, and enough to answer "how many
hospitals / schools / aerodromes / main road segments are mapped in each region".

The numbers describe what contributors have MAPPED, not what exists: the indicator names say so.
Data: © OpenStreetMap contributors, ODbL 1.0."""
from __future__ import annotations

import asyncio
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
    selector: str          # Overpass selector WITHOUT the area filter, e.g. 'nwr["amenity"="school"]'


HOSPITALS = OsmFeature("Mapped hospitals and clinics (OpenStreetMap)", "facilities",
                       'nwr["amenity"~"^(hospital|clinic)$"]')
SCHOOLS = OsmFeature("Mapped schools (OpenStreetMap)", "schools", 'nwr["amenity"="school"]')
AERODROMES = OsmFeature("Mapped aerodromes (OpenStreetMap)", "aerodromes", 'nwr["aeroway"="aerodrome"]')
MAIN_ROADS = OsmFeature("Mapped trunk and primary road segments (OpenStreetMap)", "segments",
                        'way["highway"~"^(trunk|primary)$"]')


def build_query(iso_code: str, features: list[OsmFeature], timeout: int = 90) -> str:
    """Overpass QL: the region's area, then one `out count;` per feature (answers come back in order)."""
    parts = [f'[out:json][timeout:{timeout}];', f'area["ISO3166-2"="{iso_code}"]->.a;']
    parts += [f"{f.selector}(area.a);out count;" for f in features]
    return "".join(parts)


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


REQUEST_TIMEOUT = 45.0       # seconds, per request (the query itself asks Overpass for at most 25 s)
DEADLINE_SECONDS = 180.0     # the whole collection stops here, whatever happened
CONCURRENCY = 2              # the public Overpass servers give 2 slots per address
MAX_FIRST_FAILURES = 4       # this many failures before ANY success: the source is not answering, stop


async def _query(client: httpx.AsyncClient, query: str) -> tuple[Any, str]:
    """POST one query to each server in turn (one attempt each); returns (payload or None, reason)."""
    reason = "no detail"
    for url in OVERPASS_URLS:
        try:
            response = await client.post(url, data={"data": query},
                                         headers={"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedata.td)"})
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
    empty: list[str] = []
    state: dict[str, Any] = {"ok": 0, "streak": 0, "stop": "", "reason": ""}
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(client: httpx.AsyncClient, iso: str, region: str) -> None:
        async with gate:
            remaining = deadline_seconds - (time.monotonic() - started)
            if state["stop"] or remaining <= 0:
                state["stop"] = state["stop"] or "time limit reached"
                skipped.append(region)
                return
            try:
                payload, reason = await asyncio.wait_for(_query(client, build_query(iso, features)), timeout=remaining)
            except asyncio.TimeoutError:
                state["stop"], payload, reason = "time limit reached", None, "time limit reached"
            counts = parse_counts(payload, len(features)) if payload is not None else None
            if counts is None:
                failed.append(region)
                state["reason"] = reason or "unexpected answer shape"
                state["streak"] += 1
                if state["ok"] == 0 and state["streak"] >= MAX_FIRST_FAILURES:
                    state["stop"] = "the source is not answering"
            else:
                state["ok"] += 1
                state["streak"] = 0
                if not any(counts):
                    empty.append(region)
                for feature, total in zip(features, counts):
                    if total > 0:
                        records.append({
                            "year": today.year, "month": today.month, "day": 1, "value": float(total),
                            "source": "OpenStreetMap", "indicator": feature.indicator, "unit": feature.unit,
                            "region": region, "url": "https://www.openstreetmap.org/copyright",
                        })
            await asyncio.sleep(pause)

    async with httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=15.0)) as client:
        await asyncio.gather(*(one(client, iso, region) for iso, region in REGIONS.items()))

    missing = failed + skipped
    if missing:
        stopped = f"; stopped early: {state['stop']}" if state["stop"] else ""
        errors.append(f"OpenStreetMap: {len(missing)}/{len(REGIONS)} regions did not answer "
                      f"(last reason: {state['reason'] or 'none'}{stopped}); first: {', '.join(missing[:3])}")
    if empty:
        errors.append(f"OpenStreetMap: no mapped feature found for {len(empty)} region(s): {', '.join(empty[:5])}")
    if not records:
        raise RuntimeError(errors[0] if errors else "OpenStreetMap returned nothing")
    return records
