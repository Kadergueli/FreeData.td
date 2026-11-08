from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, nasa_power_years, wb_years
from app.agents.environment import EnvironmentAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


def parse_power_energy(payload: Any, region: str, parameters: dict[str, tuple[str, str]], url: str) -> list[dict[str, Any]]:
    """Monthly records of a NASA POWER answer; the yearly mean (month 13) and the -999 gaps are dropped."""
    data = payload.get("properties", {}).get("parameter") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    records: list[dict[str, Any]] = []
    for key, (name, unit) in parameters.items():
        series = data.get(key)
        if not isinstance(series, dict):
            continue
        for stamp, value in series.items():
            if not (isinstance(value, (int, float)) and not isinstance(value, bool)) or value <= -999:
                continue
            if len(str(stamp)) != 6 or not str(stamp).isdigit() or not 1 <= int(str(stamp)[4:]) <= 12:
                continue
            records.append({"year": int(str(stamp)[:4]), "month": int(str(stamp)[4:]), "value": float(value),
                            "source": "NASA POWER", "indicator": name, "unit": unit, "region": region, "url": url})
    return records


class EnergyAgent(BaseAgent):
    """Collects energy access and consumption indicators for Chad from the
    World Bank API (World Development Indicators, sourced upstream from the
    Sustainable Energy for All / SE4ALL Global Tracking Framework led jointly
    by the World Bank, IEA, and ESMAP). Same reliable, keyless endpoint
    already used by EconomyAgent and HealthAgent, plus the solar irradiance and
    wind speed of each of the 23 regions from NASA POWER (renewable potential)."""

    sector = "energy"
    name = "EnergyAgent"

    WORLD_BANK_INDICATORS = {
        "EG.ELC.ACCS.ZS": ("Access to electricity", "% of population"),
        "EG.ELC.ACCS.RU.ZS": ("Access to electricity, rural", "% of rural population"),
        "EG.ELC.ACCS.UR.ZS": ("Access to electricity, urban", "% of urban population"),
        "EG.FEC.RNEW.ZS": ("Renewable energy consumption", "% of total final energy consumption"),
        "EG.CFT.ACCS.ZS": ("Access to clean fuels and technologies for cooking", "% of population"),
        "EG.USE.PCAP.KG.OE": ("Energy use per capita", "kg of oil equivalent"),
    }

    # NASA POWER parameter -> (indicator name, unit). Community "RE" (renewable energy).
    POWER_PARAMETERS = {
        "ALLSKY_SFC_SW_DWN": ("Solar irradiance (all-sky)", "kWh/m²/day"),
        "WS50M": ("Wind speed at 50 m", "m/s"),
    }

    # ISO3 for Chad
    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "nasa-power":
            return await self._collect_nasa_power()

        if source in ("all", "auto"):
            names = ("world-bank", "nasa-power")
            results = await asyncio.gather(self._collect_world_bank(), self._collect_nasa_power(), return_exceptions=True)
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("EnergyAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined

        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'nasa-power', 'demo'.")

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 12.0,
                "source": "World Bank",
                "indicator": "Access to electricity",
                "unit": "% of population",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 3.4,
                "source": "World Bank",
                "indicator": "Access to electricity, rural",
                "unit": "% of rural population",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 3.1,
                "source": "World Bank",
                "indicator": "Access to clean fuels and technologies for cooking",
                "unit": "% of population",
                "region": "national",
            },
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/{self.CHAD_ISO3}/indicator/{code}"
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

    async def _collect_nasa_power(self) -> list[dict[str, Any]]:
        """Monthly solar irradiance and wind speed for every region (NASA POWER, free, no key).
        A region that does not answer is listed in the run errors without hiding the others."""
        records: list[dict[str, Any]] = []
        failed: list[str] = []
        first, last = nasa_power_years(span=5)
        url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
        async with httpx.AsyncClient(timeout=60) as client:
            for region, coords in EnvironmentAgent.CHAD_REGIONS.items():
                params = {"parameters": ",".join(self.POWER_PARAMETERS), "community": "RE", "longitude": coords["lon"],
                          "latitude": coords["lat"], "start": first, "end": last, "format": "JSON"}
                reason: list[str] = []
                payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.2, errors=reason)
                parsed = parse_power_energy(payload, region, self.POWER_PARAMETERS, url) if payload is not None else []
                if parsed:
                    records.extend(parsed)
                else:
                    failed.append(f"{region} ({reason[0] if reason else 'no data'})")
        if failed:
            self.source_errors.append(f"NASA POWER: {len(failed)}/{len(EnvironmentAgent.CHAD_REGIONS)} regions empty: {'; '.join(failed[:3])}")
        if not records:
            raise RuntimeError("NASA POWER returned nothing")
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
            sector="energy",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by EnergyAgent from {record['source']}.",
        )
