from __future__ import annotations

from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, wb_years
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
    }

    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()
        if source in ("world-bank", "all", "auto"):
            return await self._collect_world_bank()
        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'demo'.")

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
        return ObservationCreate(
            sector="demography",
            indicator=str(record["indicator"]),
            value=val,
            unit=str(record.get("unit", "unit"))[:40],
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by DemographyAgent from {record['source']}.",
        )
