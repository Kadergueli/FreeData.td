"""Shared base for sectors whose data come only from the World Bank indicators API (telecom, trade)."""
from __future__ import annotations

from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, wb_years
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)

WB_URL = "https://api.worldbank.org/v2/country/TCD/indicator"


class WorldBankSectorAgent(BaseAgent):
    """One World Bank table (``WORLD_BANK_INDICATORS``: code -> (name, unit up to 40 characters))
    collected for Chad since 2000. A series with no value for Chad is skipped without error."""

    WORLD_BANK_INDICATORS: dict[str, tuple[str, str]] = {}
    DEMO: tuple[str, str, float] = ("", "", 0.0)   # indicator, unit, value

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            indicator, unit, value = self.DEMO
            return [{"year": 2023, "value": value, "source": "World Bank", "indicator": indicator,
                     "unit": unit, "region": "national"}]
        if source in ("world-bank", "all", "auto"):
            return await self._collect_world_bank()
        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'demo'.")

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"{WB_URL}/{code}"
                params = {"format": "json", "per_page": 100, "date": wb_years(2000)}
                payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.15)
                if not (isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list)):
                    continue
                for item in payload[1]:
                    if not isinstance(item, dict):
                        continue
                    val, year = item.get("value"), str(item.get("date", "")).strip()
                    if val is None or not year.isdigit():
                        continue
                    try:
                        records.append({"year": int(year), "value": round(float(val), 2), "source": "World Bank",
                                        "indicator": name, "unit": unit, "region": "national", "url": url})
                    except (ValueError, TypeError):
                        continue
        return records

    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None
        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)
        return ObservationCreate(
            sector=self.sector,
            indicator=str(record["indicator"]),
            value=val,
            unit=str(record.get("unit", "unit"))[:40],
            reference_date=date(int(record["year"]), 1, 1),
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by {self.name} from {record['source']}.",
        )
