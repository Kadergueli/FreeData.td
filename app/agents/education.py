from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, source_terms, wb_years
from app.agents.unesco_uis import UIS_INDICATORS, UIS_URL, describe_uis, parse_uis
from app.agents.unicef import collect_unicef
from app.agents.osm import HIGHER_EDUCATION, SCHOOLS, collect_osm_counts
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class EducationAgent(BaseAgent):
    """Collects education, literacy & schooling data for Chad from 4 open sources:
    1. World Bank (enrollment, literacy, completion, spending)
    2. UNESCO UIS public API (enrolment ratios, completion, out-of-school, literacy, teachers)
    3. UNICEF Data Warehouse (all-population education series, many from household surveys)
    4. OpenStreetMap (mapped schools per region)
    """

    sector = "education"
    name = "EducationAgent"

    # World Bank & UNESCO Education Indicators for Chad
    WORLD_BANK_INDICATORS = {
        "SE.PRM.NENR": ("Primary net enrollment rate", "% of school-age children"),
        "SE.SEC.NENR": ("Secondary net enrollment rate", "% of school-age children"),
        "SE.TER.ENRR": ("Tertiary gross enrollment ratio", "% of age cohort"),
        "SE.ADT.LITR.ZS": ("Adult literacy rate", "% of population age 15+"),
        "SE.YTH.LITR.ZS": ("Youth literacy rate", "% of population age 15-24"),
        "SE.ADT.LITR.FE.ZS": ("Adult female literacy rate", "% of females age 15+"),
        "SE.PRM.CMPT.ZS": ("Primary school completion rate", "% of age group"),
        "SE.XPD.TOTL.GD.ZS": ("Government expenditure on education", "% of GDP"),
        "SE.PRM.ENRL.FE.ZS": ("Primary female enrollment share", "% of total primary pupils"),
        "SE.PRM.TCHR.HD": ("Primary pupil-teacher ratio", "pupils per teacher"),
        "SE.PRM.OOSL.ZS": ("Out-of-school primary rate", "% of primary school age"),
        "SE.SEC.PROG.ZS": ("Progression rate to secondary school", "% of primary graduates"),
        "SE.PRM.REPT.ZS": ("Primary school repetition rate", "% of total enrollment"),
        "SE.ENR.PRIM.FM.ZS": ("Gender parity index in primary enrollment", "ratio (girls to boys)"),
    }

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "unesco-uis":
            return await self._collect_unesco_uis()

        if source == "unicef":
            return await self._collect_unicef_sdg4()

        if source == "open-street-map":
            return await self._collect_open_street_map()

        if source in ("all", "auto"):
            names = ("world-bank", "unesco-uis", "unicef", "open-street-map")
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_unesco_uis(),
                self._collect_unicef_sdg4(),
                self._collect_open_street_map(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("EducationAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'unesco-uis', 'unicef', 'open-street-map', 'demo'."
        )

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 78.5,
                "source": "World Bank",
                "indicator": "Primary net enrollment rate",
                "unit": "% of school-age children",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 31.2,
                "source": "UNESCO UIS",
                "indicator": "Adult literacy rate",
                "unit": "% of population age 15+",
                "region": "national",
            },
            {
                "year": 2024,
                "value": 0.76,
                "source": "UNICEF Data",
                "indicator": "Gender parity index in primary enrollment",
                "unit": "ratio (girls to boys)",
                "region": "national",
            },
        ]

    # ─── Source 1: World Bank & UNESCO Indicators ───────────────────────────
    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/TD/indicator/{code}"
                params = {"format": "json", "per_page": 50, "date": wb_years(2005)}
                payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.15)
                if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                    for item in payload[1]:
                        if not isinstance(item, dict):
                            continue
                        val = item.get("value")
                        date_str = str(item.get("date", "")).strip()
                        if val is not None and date_str.isdigit():
                            try:
                                records.append(
                                    {
                                        "year": int(date_str),
                                        "value": round(float(val), 2),
                                        "source": "World Bank",
                                        "indicator": name,
                                        "unit": unit,
                                        "region": "national",
                                        "url": url,
                                    }
                                )
                            except (ValueError, TypeError):
                                continue
        return records

    # ─── Source 2: UNESCO Institute for Statistics (UIS) ───────────────────
    async def _collect_unesco_uis(self) -> list[dict[str, Any]]:
        """UNESCO UIS series for Chad. One indicator failing is listed in the run errors without
        hiding the others; nothing at all raises so the run reports the failure."""
        records: list[dict[str, Any]] = []
        failed: list[str] = []
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for code in UIS_INDICATORS:
                reason: list[str] = []
                payload = await self.fetch_json_with_retry(
                    client, UIS_URL, params={"indicator": code, "geoUnit": "TCD"}, throttle_seconds=0.2, errors=reason)
                parsed = parse_uis(payload, code) if payload is not None else []
                if parsed:
                    records.extend(parsed)
                else:
                    failed.append(f"{code} ({reason[0] if reason else describe_uis(payload)})")
        if failed:
            self.source_errors.append(f"UNESCO UIS: {len(failed)}/{len(UIS_INDICATORS)} series empty: {'; '.join(failed[:4])}")
        if not records:
            raise RuntimeError("UNESCO UIS returned nothing")
        return records

    # ─── Source 3: UNICEF Data Warehouse (SDMX) ─────────────────────────────
    async def _collect_unicef_sdg4(self) -> list[dict[str, Any]]:
        """Every all-population UNICEF education series for Chad (completion, out-of-school, attendance...)."""
        return await collect_unicef("education", self.source_errors)

    # ─── Source 4: OpenStreetMap (Overpass) ──────────────────────────────────
    async def _collect_open_street_map(self) -> list[dict[str, Any]]:
        """Mapped schools, universities and colleges per region (OpenStreetMap contributors)."""
        return await collect_osm_counts([SCHOOLS, HIGHER_EDUCATION], self.source_errors)

    # ─── Normalize ───────────────────────────────────────────────────────────
    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None

        yr = int(record["year"])
        mo = int(record.get("month", 1))
        dy = int(record.get("day", 1))
        ref_date = date(yr, mo, dy)
        unit_str = str(record.get("unit", "unit"))[:30]

        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)

        licence, notes = source_terms(str(record["source"]), "EducationAgent")
        return ObservationCreate(
            sector="education",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license=licence,
            notes=notes,
        )
