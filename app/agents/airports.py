"""Airports of Chad from OurAirports (public-domain CSV, no key, no rate limit).

    https://davidmegginson.github.io/ourairports-data/airports.csv

One row per airport/airstrip/heliport worldwide, with its ISO 3166-2 region (`TD-LC`...), type and
whether it has scheduled service. Replaces the OpenStreetMap aerodrome count, which the public
Overpass servers could not answer in a reasonable time. Counts are snapshots, stored monthly.
"""
from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO
from typing import Any

from app.agents.osm import REGIONS

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
SOURCE_LABEL = "OurAirports"
LANDING_TYPES = ("large_airport", "medium_airport", "small_airport")      # no heliports, no closed fields


def parse_airports(text: str, today: datetime | None = None) -> list[dict[str, Any]]:
    """Raw records: airports and airstrips per region, and national totals (all / scheduled service)."""
    today = today or datetime.now(UTC)
    per_region: dict[str, int] = {}
    total = scheduled = 0
    for row in csv.DictReader(StringIO(text.lstrip("\ufeff"))):
        if row.get("iso_country") != "TD" or row.get("type") not in LANDING_TYPES:
            continue
        total += 1
        if str(row.get("scheduled_service", "")).lower() == "yes":
            scheduled += 1
        region = REGIONS.get(str(row.get("iso_region", "")).strip())
        if region:
            per_region[region] = per_region.get(region, 0) + 1

    base = {"year": today.year, "month": today.month, "day": 1, "source": SOURCE_LABEL,
            "unit": "airports", "url": "https://ourairports.com/countries/TD/"}
    records = [{**base, "value": float(n), "indicator": "Airports and airstrips (OurAirports)", "region": region}
               for region, n in per_region.items()]
    if total:
        records.append({**base, "value": float(total), "indicator": "Airports and airstrips (OurAirports)", "region": "national"})
        records.append({**base, "value": float(scheduled), "indicator": "Airports with scheduled service (OurAirports)",
                        "region": "national"})
    return records
