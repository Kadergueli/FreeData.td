"""UNICEF Data Warehouse (SDMX, no key): official UNICEF series for Chad.

    GET https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/UNICEF,{flow},1.0/TCD..?format=csv&labels=both

The answer is a CSV with one row per indicator, year and breakdown (sex, wealth quintile, residence...).
Only the all-population rows are kept. Indicator names and units come from the data itself, so the
platform never shows a name that does not match the code. A year can come from several surveys:
the first row wins.
"""
from __future__ import annotations

import csv
import io
from typing import Any

UNICEF_URL = "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/UNICEF,{flow},1.0/TCD.."
SOURCE = "UNICEF Data"
FIRST_YEAR = 1960

# Dataflows collected, by sector. Verified to hold data for Chad (Nov 2026).
FLOWS_BY_SECTOR: dict[str, tuple[str, ...]] = {"education": ("EDUCATION",)}

# Columns that split a figure into groups: a row is "all population" when each of them is total or absent.
BREAKDOWNS = ("SEX", "WEALTH_QUINTILE", "RESIDENCE", "MATERNAL_EDU_LVL")
TOTAL = ("_T", "")


def is_total(row: dict[str, str]) -> bool:
    return all((row.get(col) or "").strip() in TOTAL for col in BREAKDOWNS)


def parse_unicef(text: str, flow: str) -> list[dict[str, Any]]:
    """One record per indicator and year from a UNICEF SDMX CSV; [] when it has not the expected columns."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"INDICATOR", "TIME_PERIOD", "OBS_VALUE"} <= set(reader.fieldnames):
        return []
    seen: set[tuple[str, int]] = set()
    records: list[dict[str, Any]] = []
    for row in reader:
        if not is_total(row):
            continue
        code = (row.get("INDICATOR") or "").strip()
        period = (row.get("TIME_PERIOD") or "").strip()
        try:
            year, value = int(period[:4]), float(row["OBS_VALUE"])
        except (ValueError, TypeError, KeyError):
            continue
        if not code or year < FIRST_YEAR or (code, year) in seen:
            continue
        seen.add((code, year))
        name = (row.get("Indicator") or code).strip()[:120]
        unit = (row.get("Unit of measure") or row.get("UNIT_MEASURE") or "value").strip()[:40]
        records.append({"year": year, "value": round(value, 2), "source": SOURCE, "indicator": name, "unit": unit,
                        "region": "national", "url": UNICEF_URL.format(flow=flow)})
    return records
