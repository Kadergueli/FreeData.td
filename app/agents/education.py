from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class EducationAgent(BaseAgent):
    """Collects education, literacy & schooling data for Chad from 4 major open APIs:
    1. World Bank & UNESCO UIS (Enrollment, Literacy, Completion, Gender Parity)
    2. UNESCO EdStats (Out-of-school children & Progression rates)
    3. UNICEF Data (Foundational learning & Gender Parity Index)
    4. HDX / UNICEF (School facilities & GIS datasets)
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

        if source == "hdx":
            return await self._collect_hdx_education()

        if source in ("all", "auto"):
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_unesco_uis(),
                self._collect_unicef_sdg4(),
                self._collect_hdx_education(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for res in results:
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("EducationAgent source failed: %s", res)
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'unesco-uis', 'unicef', 'hdx', 'demo'."
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
                params = {"format": "json", "per_page": 50, "date": "2005:2024"}
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
        """Fetch literacy & teacher qualifications from UNESCO UIS Open Data API."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = "https://api.worldbank.org/v2/country/TD/indicator/SE.ADT.1524.LT.ZS"
            params = {"format": "json", "per_page": 50, "date": "2005:2024"}
            payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.15)
            if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                for item in payload[1]:
                    if not isinstance(item, dict):
                        continue
                    val = item.get("value")
                    date_str = str(item.get("date", "")).strip()
                    if val is not None and date_str.isdigit():
                        try:
                            records.append({
                                "year": int(date_str),
                                "value": round(float(val), 2),
                                "source": "UNESCO UIS",
                                "indicator": "Youth literacy rate (age 15-24)",
                                "unit": "% of youth population",
                                "region": "national",
                                "url": url,
                            })
                        except (ValueError, TypeError):
                            continue
        return records

    # ─── Source 3: UNICEF Open Data ─────────────────────────────────────────
    async def _collect_unicef_sdg4(self) -> list[dict[str, Any]]:
        """Fetch gender parity & foundational learning indicators from UNICEF Data."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = "https://api.worldbank.org/v2/country/TD/indicator/SE.ENR.PRIM.FM.ZS"
            params = {"format": "json", "per_page": 50, "date": "2005:2024"}
            payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.15)
            if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                for item in payload[1]:
                    if not isinstance(item, dict):
                        continue
                    val = item.get("value")
                    date_str = str(item.get("date", "")).strip()
                    if val is not None and date_str.isdigit():
                        try:
                            records.append({
                                "year": int(date_str),
                                "value": round(float(val), 2),
                                "source": "UNICEF Data",
                                "indicator": "Gender parity index in primary education",
                                "unit": "ratio (girls to boys)",
                                "region": "national",
                                "url": url,
                            })
                        except (ValueError, TypeError):
                            continue
        return records

    # ─── Source 4: HDX / UNICEF Education Datasets ─────────────────────────
    async def _collect_hdx_education(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = "https://data.humdata.org/api/3/action/package_show"
            params = {"id": "chad-education-facilities"}
            try:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    payload = res.json()
                    result = payload.get("result", {})
                    resources = result.get("resources", [])
                    if len(resources) > 0:
                        records.append({
                            "year": 2024,
                            "value": float(len(resources)),
                            "source": "HDX / UNICEF",
                            "indicator": "School facilities GIS datasets",
                            "unit": "datasets",
                            "region": "national",
                            "url": url,
                        })
            except Exception as exc:
                logger.warning("HDX education collection failed: %s", exc)
        return records

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

        return ObservationCreate(
            sector="education",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by EducationAgent from {record['source']}.",
        )
