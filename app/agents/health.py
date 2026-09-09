from __future__ import annotations

from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class HealthAgent(BaseAgent):
    """Collects public health indicators for Chad from the World Bank API
    (World Development Indicators, sourced upstream from WHO/UNICEF/national
    surveys). Reuses the same reliable, keyless, well-documented endpoint
    already used by EconomyAgent — no dependency on the WHO GHO OData API,
    which WHO itself has flagged as deprecated since end of 2025."""

    sector = "health"
    name = "HealthAgent"

    WORLD_BANK_INDICATORS = {
        "SP.DYN.LE00.IN": ("Life expectancy at birth", "years"),
        "SH.DYN.MORT": ("Under-5 mortality rate", "per 1,000 live births"),
        "SH.STA.MMRT": ("Maternal mortality ratio", "per 100,000 live births"),
        "SH.XPD.CHEX.GD.ZS": ("Current health expenditure", "% of GDP"),
        "SH.STA.BRTC.ZS": ("Births attended by skilled health staff", "% of total"),
        "SH.STA.STNT.ZS": ("Stunting prevalence, children under 5", "% of children under 5"),
        "SH.H2O.BASW.ZS": ("Access to basic drinking water services", "% of population"),
        "SH.STA.BASS.ZS": ("Access to basic sanitation services", "% of population"),
    }

    # ISO3 for Chad
    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source in ("world-bank", "all", "auto"):
            return await self._collect_world_bank()

        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'demo'.")

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 53.0,
                "source": "World Bank",
                "indicator": "Life expectancy at birth",
                "unit": "years",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 105.9,
                "source": "World Bank",
                "indicator": "Under-5 mortality rate",
                "unit": "per 1,000 live births",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 748.0,
                "source": "World Bank",
                "indicator": "Maternal mortality ratio",
                "unit": "per 100,000 live births",
                "region": "national",
            },
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/{self.CHAD_ISO3}/indicator/{code}"
                params = {"format": "json", "per_page": 50, "date": "2015:2024"}
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

    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None

        yr = int(record["year"])
        mo = int(record.get("month", 1))
        dy = int(record.get("day", 1))
        ref_date = date(yr, mo, dy)
        unit_str = str(record.get("unit", "unit"))[:40]

        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)

        return ObservationCreate(
            sector="health",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by HealthAgent from {record['source']}.",
        )
