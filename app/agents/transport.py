from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, recent_window, source_terms, wb_years
from app.agents.osm import AERODROMES, MAIN_ROADS, collect_osm_counts
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class TransportAgent(BaseAgent):
    """Collects transport, logistics & infrastructure data for Chad from 3 open sources:
    1. World Bank (Road network, Paved ratio, Air transport, LPI)
    2. OpenStreetMap Overpass (mapped trunk/primary road segments and aerodromes, per region)
    3. Open-Meteo Transport (Visibility & precipitation risk along transport corridors)
    """

    sector = "transport"
    name = "TransportAgent"

    # World Bank Transport & Logistics Indicators for Chad
    WORLD_BANK_INDICATORS = {
        "IS.ROD.PAVE.ZS": ("Paved roads ratio", "% of total road network"),
        "IS.ROD.TOTL.KM": ("Total road network length", "km"),
        "IS.AIR.DSTR.VF": ("Air transport carrier departures", "registered flights"),
        "IS.AIR.PSGR": ("Air transport passengers carried", "passengers"),
        "IS.AIR.GOOD.MT.K1": ("Air freight transport", "million ton-km"),
        "LP.LPI.OVRL.XQ": ("Logistics Performance Index", "score (1-5)"),
        "LP.LPI.INFR.XQ": ("Transport infrastructure quality index", "score (1-5)"),
    }

    # Major trade & transport hubs in Chad with GPS coordinates
    TRANSPORT_HUBS = {
        "N'Djamena (Chari-Baguirmi)": {"lat": 12.11, "lon": 15.05, "hub_type": "Capitale / Hub Aérien et Routier"},
        "Moundou (Logone Occidental)": {"lat": 8.56, "lon": 16.08, "hub_type": "Hub Industriel et Cotonnier"},
        "Sarh (Moyen-Chari)": {"lat": 9.15, "lon": 18.39, "hub_type": "Hub Agricole du Sud-Est"},
        "Abéché (Ouaddaï)": {"lat": 13.82, "lon": 20.83, "hub_type": "Hub Commercial de l'Est"},
        "Faya-Largeau (Borkou)": {"lat": 17.93, "lon": 19.11, "hub_type": "Hub Logistique du Nord"},
    }

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "open-street-map":
            return await self._collect_open_street_map()

        if source == "open-meteo-transport":
            return await self._collect_open_meteo_transport()

        if source in ("all", "auto"):
            names = ("world-bank", "open-street-map", "open-meteo-transport")
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_open_street_map(),
                self._collect_open_meteo_transport(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("TransportAgent source %s failed: %s", name, res)
                    self.source_errors.append(f"{name}: {res}")
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'open-street-map', 'open-meteo-transport', 'demo'."
        )

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 40000.0,
                "source": "World Bank",
                "indicator": "Total road network length",
                "unit": "km",
                "region": "national",
            },
            {
                "year": 2024,
                "value": 14.5,
                "source": "OpenStreetMap",
                "indicator": "Primary transport corridors",
                "unit": "major routes",
                "region": "national",
            },
            {
                "year": 2024,
                "value": 6.0,
                "source": "HDX / UN OCHA",
                "indicator": "Logistics cluster road datasets",
                "unit": "datasets",
                "region": "national",
            },
        ]

    # ─── Source 1: World Bank Transport ─────────────────────────────────────
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

    # ─── Source 2: OpenStreetMap (Overpass) ──────────────────────────────────
    async def _collect_open_street_map(self) -> list[dict[str, Any]]:
        """Mapped main-road segments and aerodromes per region (OpenStreetMap contributors)."""
        return await collect_osm_counts([MAIN_ROADS, AERODROMES], self.source_errors)

    # ─── Source 4: Open-Meteo Transport Weather Risk ───────────────────────
    async def _collect_open_meteo_transport(self) -> list[dict[str, Any]]:
        """Fetch transport corridor weather risk (visibility & heavy rainfall) for Chad hubs."""
        records: list[dict[str, Any]] = []
        window = recent_window(months=6)
        async with httpx.AsyncClient(timeout=30) as client:
            for hub_name, coords in self.TRANSPORT_HUBS.items():
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": coords["lat"],
                    "longitude": coords["lon"],
                    "start_date": window[0],
                    "end_date": window[1],
                    "daily": "precipitation_sum,wind_speed_10m_max",
                    "timezone": "Africa/Ndjamena",
                }
                try:
                    res = await client.get(url, params=params)
                    res.raise_for_status()
                    daily = res.json().get("daily", {})
                    precip = daily.get("precipitation_sum", [])
                    wind = daily.get("wind_speed_10m_max", [])

                    # Compute heavy rain days (>10mm) and high wind days (>30km/h)
                    heavy_rain_days = sum(1 for p in precip if p is not None and p > 10.0)
                    high_wind_days = sum(1 for w in wind if w is not None and w > 30.0)

                    records.append({
                        "year": 2024,
                        "value": float(heavy_rain_days),
                        "source": "Open-Meteo Transport",
                        "indicator": "Corridor flood risk days (>10mm rain)",
                        "unit": "days",
                        "region": hub_name,
                        "url": url,
                    })
                    records.append({
                        "year": 2024,
                        "value": float(high_wind_days),
                        "source": "Open-Meteo Transport",
                        "indicator": "Corridor dust storm risk days (>30km/h wind)",
                        "unit": "days",
                        "region": hub_name,
                        "url": url,
                    })
                except Exception as exc:
                    logger.warning("Open-Meteo transport risk failed for %s: %s", hub_name, exc)

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

        licence, notes = source_terms(str(record["source"]), "TransportAgent")
        return ObservationCreate(
            sector="transport",
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
