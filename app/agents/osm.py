"""OpenStreetMap feature counts per administrative region of Chad (Overpass API).

One small query per region (23 + N'Djamena), looked up by the region's ISO 3166-2 code, returning
only counts (`out count`): light for the public Overpass servers, and enough to answer "how many
hospitals / schools / aerodromes / main road segments are mapped in each region".

The numbers describe what contributors have MAPPED, not what exists: the indicator names say so.
Data: © OpenStreetMap contributors, ODbL 1.0."""
from __future__ import annotations

import asyncio
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


async def _query(client: httpx.AsyncClient, query: str) -> tuple[Any, str]:
    """POST one query, trying each server; returns (payload or None, reason of the last failure)."""
    reason = "no detail"
    for url in OVERPASS_URLS:
        for attempt in (1, 2):
            try:
                response = await client.post(url, data={"data": query},
                                             headers={"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedata.td)"})
                if response.status_code == 200:
                    return response.json(), ""
                reason = f"HTTP {response.status_code}"
                if response.status_code in (429, 504) and attempt == 1:
                    await asyncio.sleep(8)       # busy server: wait for a free slot, once
                    continue
                break
            except (httpx.RequestError, ValueError) as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:100] or 'no detail'}"
                break
    return None, reason


async def collect_osm_counts(features: list[OsmFeature], errors: list[str], pause: float = 1.5) -> list[dict[str, Any]]:
    """Counts of the given features for every region, as raw records (monthly snapshots).

    A region whose answer is missing is skipped and counted in `errors`; a region where EVERY
    count is zero is also skipped (the ISO area was not found, which is not "nothing mapped").
    Raises RuntimeError when no region answered at all, so the run reports the source as failed."""
    today = datetime.now(UTC)
    records: list[dict[str, Any]] = []
    failed: list[str] = []
    empty: list[str] = []
    last_reason = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as client:
        for iso, region in REGIONS.items():
            payload, reason = await _query(client, build_query(iso, features))
            counts = parse_counts(payload, len(features)) if payload is not None else None
            if counts is None:
                failed.append(region)
                last_reason = reason or "unexpected answer shape"
            elif not any(counts):
                empty.append(region)
            else:
                for feature, total in zip(features, counts):
                    if total > 0:
                        records.append({
                            "year": today.year, "month": today.month, "day": 1, "value": float(total),
                            "source": "OpenStreetMap", "indicator": feature.indicator, "unit": feature.unit,
                            "region": region, "url": "https://www.openstreetmap.org/copyright",
                        })
            await asyncio.sleep(pause)
    if failed:
        errors.append(f"OpenStreetMap: {len(failed)}/{len(REGIONS)} regions did not answer "
                      f"(last reason: {last_reason}); first: {', '.join(failed[:3])}")
    if empty:
        errors.append(f"OpenStreetMap: no mapped feature found for {len(empty)} region(s): {', '.join(empty[:5])}")
    if not records:
        raise RuntimeError(errors[0] if errors else "OpenStreetMap returned nothing")
    return records
