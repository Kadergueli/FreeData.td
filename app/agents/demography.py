from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, source_terms, wb_years
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class DemographyAgent(BaseAgent):
    """Population and demographic indicators for Chad from the World Bank API (World Development
    Indicators, built upstream from the UN Population Division and national censuses).

    The finer national statistics (age pyramid, by province) come from INSEED through
    `python -m app.cli import-inseed`; this agent gives the long annual series that need no
    manual step."""

    sector = "demography"
    name = "DemographyAgent"

    WORLD_BANK_INDICATORS = {
        "SP.POP.TOTL": ("Total population", "inhabitants"),
        "SP.POP.GROW": ("Population growth rate", "% per year"),
        "SP.URB.TOTL.IN.ZS": ("Urban population share", "% of population"),
        "SP.RUR.TOTL.ZS": ("Rural population share", "% of population"),
        "SP.POP.0014.TO.ZS": ("Population aged 0-14", "% of population"),
        "SP.POP.1564.TO.ZS": ("Population aged 15-64", "% of population"),
        "SP.POP.65UP.TO.ZS": ("Population aged 65 and over", "% of population"),
        "SP.POP.DPND": ("Age dependency ratio", "% of working-age population"),
        "SP.DYN.CBRT.IN": ("Crude birth rate", "per 1,000 people"),
        "SP.DYN.CDRT.IN": ("Crude death rate", "per 1,000 people"),
        "SP.DYN.TFRT.IN": ("Fertility rate", "births per woman"),
        "SM.POP.NETM": ("Net migration", "people"),
        "EN.POP.DNST": ("Population density", "people per km²"),
        "SM.POP.TOTL.ZS": ("International migrant stock", "% of population"),
    }

    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()
        if source == "world-bank":
            return await self._collect_world_bank()
        if source == "unhcr":
            return await self._collect_unhcr()
        if source in ("all", "auto"):
            names = ("world-bank", "unhcr")
            results = await asyncio.gather(self._collect_world_bank(), self._collect_unhcr(), return_exceptions=True)
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("DemographyAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined
        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'unhcr', 'demo'.")

    UNHCR_URL = "https://api.unhcr.org/population/v1/population/"

    @staticmethod
    def _count(value: Any) -> int:
        """UNHCR writes '-' (or nothing) where there is no figure."""
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    async def _unhcr_items(self, client: httpx.AsyncClient, extra: dict[str, str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page, pages = 1, 1
        while page <= pages and page <= 20:
            params = {"limit": 1000, "page": page, "yearFrom": 2000, "yearTo": datetime.now(UTC).year,
                      "cf_type": "ISO", **extra}
            payload = await self.fetch_json_with_retry(client, self.UNHCR_URL, params=params, throttle_seconds=0.2)
            if not isinstance(payload, dict):
                break
            items.extend(x for x in payload.get("items", []) if isinstance(x, dict))
            try:
                pages = int(payload.get("maxPages") or 1)
            except (TypeError, ValueError):
                pages = 1
            page += 1
        return items

    async def _collect_unhcr(self) -> list[dict[str, Any]]:
        """Forced displacement from the UNHCR population statistics (end-of-year stocks):
        people hosted in Chad (by country of origin), internally displaced, and Chadians abroad."""
        async with httpx.AsyncClient(timeout=60) as client:
            hosted = await self._unhcr_items(client, {"coa": self.CHAD_ISO3, "coo_all": "true"})
            abroad = await self._unhcr_items(client, {"coo": self.CHAD_ISO3, "coa_all": "true"})
        return self.unhcr_records(hosted, abroad)

    def unhcr_records(self, hosted: list[dict[str, Any]], abroad: list[dict[str, Any]]) -> list[dict[str, Any]]:
        today = datetime.now(UTC).date()
        totals: dict[tuple[int, str], int] = {}
        records: list[dict[str, Any]] = []

        def put(year: int, indicator: str, value: int, url: str = self.UNHCR_URL) -> None:
            if value > 0:
                records.append({"year": year, "month": 12 if year < today.year else today.month,
                                "day": 31 if year < today.year else today.day, "value": float(value),
                                "source": "UNHCR", "indicator": indicator, "unit": "people",
                                "region": "national", "url": url})

        for it in hosted:
            try:
                year = int(it.get("year"))
            except (TypeError, ValueError):
                continue
            if it.get("coo_iso") == self.CHAD_ISO3:                      # Chadians displaced inside Chad
                totals[(year, "Internally displaced persons in Chad")] = (
                    totals.get((year, "Internally displaced persons in Chad"), 0) + self._count(it.get("idps")))
                continue
            refugees = self._count(it.get("refugees"))
            totals[(year, "Refugees hosted in Chad")] = totals.get((year, "Refugees hosted in Chad"), 0) + refugees
            totals[(year, "Asylum seekers in Chad")] = (
                totals.get((year, "Asylum seekers in Chad"), 0) + self._count(it.get("asylum_seekers")))
            origin = str(it.get("coo_name") or "").strip()
            if origin:
                put(year, f"Refugees from {origin} in Chad", refugees)
        for it in abroad:
            try:
                year = int(it.get("year"))
            except (TypeError, ValueError):
                continue
            if it.get("coa_iso") == self.CHAD_ISO3:
                continue
            for field, label in (("refugees", "Chadian refugees abroad"), ("asylum_seekers", "Chadian asylum seekers abroad")):
                totals[(year, label)] = totals.get((year, label), 0) + self._count(it.get(field))
        for (year, indicator), value in totals.items():
            put(year, indicator, value)
        return records

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {"year": 2023, "value": 18278568.0, "source": "World Bank", "indicator": "Total population",
             "unit": "inhabitants", "region": "national"},
            {"year": 2023, "value": 3.0, "source": "World Bank", "indicator": "Population growth rate",
             "unit": "% per year", "region": "national"},
            {"year": 2023, "value": 24.0, "source": "World Bank", "indicator": "Urban population share",
             "unit": "% of population", "region": "national"},
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/{self.CHAD_ISO3}/indicator/{code}"
                params = {"format": "json", "per_page": 80, "date": wb_years(2000)}
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
                                    "year": int(date_str), "value": round(float(val), 2), "source": "World Bank",
                                    "indicator": name, "unit": unit, "region": "national", "url": url,
                                })
                            except (ValueError, TypeError):
                                continue
        return records

    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None
        ref_date = date(int(record["year"]), int(record.get("month", 1)), int(record.get("day", 1)))
        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)
        licence, notes = source_terms(str(record["source"]), "DemographyAgent")
        return ObservationCreate(
            sector="demography",
            indicator=str(record["indicator"]),
            value=val,
            unit=str(record.get("unit", "unit"))[:40],
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license=licence,
            notes=notes,
        )
