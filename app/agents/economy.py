from __future__ import annotations

from datetime import date
import logging
from typing import Any

import asyncio

import httpx

from app.agents.base import BaseAgent, source_terms, wb_years
from app.agents.imf import IMF_INDICATORS, IMF_URL, parse_imf
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

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "imf":
            return await self._collect_imf()

        if source in ("all", "auto"):
            names = ("world-bank", "imf")
            results = await asyncio.gather(self._collect_world_bank(), self._collect_imf(), return_exceptions=True)
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("EconomyAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined

        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'imf', 'demo'.")

    async def _collect_imf(self) -> list[dict[str, Any]]:
        """IMF World Economic Outlook series (growth, inflation, debt, revenue, current account...).

        Raises when no indicator could be read, so the run reports the failure; one indicator
        failing is listed in the run errors without hiding the others."""
        records: list[dict[str, Any]] = []
        failed: list[str] = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for code in IMF_INDICATORS:
                reason: list[str] = []
                payload = await self.fetch_json_with_retry(
                    client, f"{IMF_URL}/{code}/TCD", throttle_seconds=0.3, errors=reason)
                parsed = parse_imf(payload, code) if payload is not None else []
                if parsed:
                    records.extend(parsed)
                else:
                    failed.append(f"{code} ({reason[0] if reason else 'no data for Chad'})")
        if failed:
            self.source_errors.append(f"IMF: {len(failed)}/{len(IMF_INDICATORS)} series empty: {'; '.join(failed[:4])}")
        if not records:
            raise RuntimeError("IMF DataMapper returned nothing")
        return records

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
                params = {"format": "json", "per_page": 50, "date": wb_years(2015)}
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

        licence, notes = source_terms(str(record["source"]), "EconomyAgent")
        return ObservationCreate(
            sector="economy",
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
