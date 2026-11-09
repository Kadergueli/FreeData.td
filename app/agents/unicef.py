"""UNICEF Data Warehouse (SDMX, no key): official UNICEF series for Chad.

    GET https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/UNICEF,{flow},1.0/TCD..?format=csv&labels=both

The answer is a CSV with one row per indicator, year and breakdown (sex, wealth quintile, residence...).
Only the all-population rows are kept. Indicator names and units come from the data itself, so the
platform never shows a name that does not match the code. A year can come from several surveys:
the first row wins.
"""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import UTC, datetime
from typing import Any

import httpx

UNICEF_URL = "https://sdmx.data.unicef.org/ws/public/sdmxapi/rest/data/UNICEF,{flow},1.0/TCD.."
SOURCE = "UNICEF Data"
FIRST_YEAR = 1960
MAX_NAME = 100  # the indicator column of the database holds 100 characters

# Dataflows collected, by sector. Verified to hold data for Chad (Nov 2026).
# Health keeps nutrition and immunisation: mortality and water/sanitation already come from WHO and the World Bank.
FLOWS_BY_SECTOR: dict[str, tuple[str, ...]] = {"education": ("EDUCATION",), "health": ("NUTRITION", "IMMUNISATION")}

# Columns that split a figure into groups: a row is "all population" when each of them is total or absent.
BREAKDOWNS = ("SEX", "WEALTH_QUINTILE", "RESIDENCE", "MATERNAL_EDU_LVL", "HEAD_OF_HOUSE")
TOTAL = ("_T", "")
NATIONAL_LEVELS = ("C", "_T", "")  # REPORTING_LVL: "C" is the country level


def is_total(row: dict[str, str]) -> bool:
    if (row.get("REPORTING_LVL") or "").strip() not in NATIONAL_LEVELS:
        return False
    return all((row.get(col) or "").strip() in TOTAL for col in BREAKDOWNS)


def _priority(row: dict[str, str]) -> float:
    try:
        return float(row.get("DATA_SOURCE_PRIORITY") or 99)
    except ValueError:
        return 99.0


def _pick(rows: list[dict[str, str]]) -> dict[str, str] | None:
    """The row that stands for the whole population of one indicator and year.

    A survey publishes the same figure for many age groups. The all-ages row (AGE=_T) is the figure for
    the whole group the indicator describes; without it, a single age group is accepted (the indicator is
    defined for that group, e.g. DTP3 at 12-23 months), and several different ones are ambiguous: skipped
    rather than guessed. Several surveys in one year: the best data-source priority, then the first.
    """
    all_ages = [r for r in rows if (r.get("AGE") or "").strip() in TOTAL]
    if all_ages:
        return min(all_ages, key=_priority)
    if len({(r.get("AGE") or "").strip() for r in rows}) == 1:
        return min(rows, key=_priority)
    return None


def parse_unicef(text: str, flow: str) -> list[dict[str, Any]]:
    """One record per indicator and year from a UNICEF SDMX CSV; [] when it has not the expected columns."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"INDICATOR", "TIME_PERIOD", "OBS_VALUE"} <= set(reader.fieldnames):
        return []
    last_year = datetime.now(UTC).year
    groups: dict[tuple[str, int], list[dict[str, str]]] = {}
    for row in reader:
        if not is_total(row):
            continue
        code = (row.get("INDICATOR") or "").strip()
        try:
            year = int((row.get("TIME_PERIOD") or "").strip()[:4])
            float(row["OBS_VALUE"])
        except (ValueError, TypeError, KeyError):
            continue
        # TRGT_* rows are targets for a future year, not measurements.
        if code and FIRST_YEAR <= year <= last_year and not code.startswith("TRGT_"):
            groups.setdefault((code, year), []).append(row)
    records: list[dict[str, Any]] = []
    for (code, year), rows in groups.items():
        row = _pick(rows)
        if row is None:
            continue
        name = (row.get("Indicator") or code).strip()[:MAX_NAME]
        unit = (row.get("Unit of measure") or row.get("UNIT_MEASURE") or "value").strip()[:40]
        records.append({"year": year, "value": round(float(row["OBS_VALUE"]), 2), "source": SOURCE, "indicator": name,
                        "unit": unit, "region": "national", "url": UNICEF_URL.format(flow=flow)})
    return records


async def collect_unicef(sector: str, errors: list[str]) -> list[dict[str, Any]]:
    """Every all-population UNICEF series of the sector's dataflows for Chad. A dataflow that fails
    is listed in `errors` without hiding the others; nothing at all raises so the run reports it."""
    records: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        for flow in FLOWS_BY_SECTOR[sector]:
            text, last_error = None, "no answer"
            for attempt in range(3):
                try:
                    resp = await client.get(UNICEF_URL.format(flow=flow), params={"format": "csv", "labels": "both"},
                                            headers={"User-Agent": "FreeData.td Open Data Engine/1.0"})
                    if resp.status_code == 200:
                        text = resp.text
                        break
                    last_error = f"HTTP {resp.status_code}"
                except httpx.HTTPError as exc:
                    last_error = type(exc).__name__
                await asyncio.sleep(2 * (attempt + 1))
            if text is None:
                errors.append(f"UNICEF {flow}: {last_error}")
                continue
            parsed = parse_unicef(text, flow)
            if not parsed:
                errors.append(f"UNICEF {flow}: answer without usable rows")
            records.extend(parsed)
    if not records:
        raise RuntimeError("UNICEF returned nothing")
    return records
