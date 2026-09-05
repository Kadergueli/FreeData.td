from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class EconomyAgent(BaseAgent):
    """Collects macroeconomic indicators for Chad from World Bank API."""

    sector = "economy"
    name = "EconomyAgent"

    # Macroeconomic & fiscal World Bank indicators for Chad
    WORLD_BANK_INDICATORS = {
        "NY.GDP.MKTP.CD": ("GDP current USD", "USD"),
        "NY.GDP.MKTP.KD.ZG": ("GDP real growth annual", "%"),
        "NY.GDP.PCAP.CD": ("GDP per capita current USD", "USD"),
        "FP.CPI.TOTL.ZG": ("Inflation consumer prices annual", "%"),
        "GC.REV.XAGT.GD.ZS": ("Tax revenue", "% of GDP"),
        "DT.DOD.DECT.GN.ZS": ("External debt stocks", "% of GNI"),
        "BX.TRF.PWKR.DT.GD.ZS": ("Personal remittances received", "% of GDP"),
    }

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
                "value": 12700000000.0,
                "source": "World Bank",
                "indicator": "GDP current USD",
                "unit": "USD",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 4.1,
                "source": "World Bank",
                "indicator": "GDP real growth annual",
                "unit": "%",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 719.5,
                "source": "World Bank",
                "indicator": "GDP per capita current USD",
                "unit": "USD",
                "region": "national",
            },
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/TD/indicator/{code}"
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
        unit_str = str(record.get("unit", "unit"))[:30]

        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)

        return ObservationCreate(
            sector="economy",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by EconomyAgent from {record['source']}.",
        )
