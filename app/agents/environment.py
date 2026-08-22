from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.config import settings
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class EnvironmentAgent(BaseAgent):
    """Collects environmental data for Chad: weather (temp, precipitation) and bush fires (NASA FIRMS)."""

    sector = "environment"
    name = "EnvironmentAgent"

    # ─── Chad regions with GPS coordinates ────────────────────────────────────
    CHAD_REGIONS = {
        "N'Djamena (Chari-Baguirmi)": {"lat": 12.11, "lon": 15.05},
        "Moundou (Logone Occidental)": {"lat": 8.56, "lon": 16.08},
        "Sarh (Moyen-Chari)": {"lat": 9.15, "lon": 18.39},
        "Abéché (Ouaddaï)": {"lat": 13.82, "lon": 20.83},
        "Mao (Kanem)": {"lat": 14.12, "lon": 15.31},
        "Faya-Largeau (Borkou)": {"lat": 17.93, "lon": 19.11},
    }

    # Chad bounding box for NASA FIRMS (lat/lon)
    CHAD_BBOX = {"west": 13.5, "south": 7.4, "east": 24.0, "north": 23.5}

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "open-meteo":
            return await self._collect_open_meteo_weather()

        if source == "nasa-power":
            return await self._collect_nasa_power()

        if source == "nasa-firms":
            return await self._collect_nasa_firms()

        if source in ("all", "auto"):
            results = await asyncio.gather(
                self._collect_open_meteo_weather(),
                self._collect_nasa_power(),
                self._collect_nasa_firms(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for res in results:
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("EnvironmentAgent source failed: %s", res)
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'open-meteo', 'nasa-power', 'nasa-firms'."
        )

    # ─── Source 1: Open-Meteo Archive (temperature + precipitation) ──────────
    async def _collect_open_meteo_weather(self) -> list[dict[str, Any]]:
        """Daily temperature & precipitation from Open-Meteo Archive API (free, no key)."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for region_name, coords in self.CHAD_REGIONS.items():
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": coords["lat"],
                    "longitude": coords["lon"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "Africa/Ndjamena",
                }
                try:
                    res = await client.get(url, params=params)
                    res.raise_for_status()
                    daily = res.json().get("daily", {})
                    dates = daily.get("time", [])
                    temp_mean = daily.get("temperature_2m_mean", [])
                    temp_max = daily.get("temperature_2m_max", [])
                    temp_min = daily.get("temperature_2m_min", [])
                    precip = daily.get("precipitation_sum", [])

                    for i, dt_str in enumerate(dates):
                        yr = int(dt_str[:4])
                        mo = int(dt_str[5:7])
                        dy = int(dt_str[8:10])
                        base = {
                            "year": yr, "month": mo, "day": dy,
                            "region": region_name,
                            "source": "Open-Meteo Archive",
                            "url": url,
                        }

                        if i < len(temp_mean) and temp_mean[i] is not None:
                            records.append({**base, "indicator": "Daily mean temperature", "value": float(temp_mean[i]), "unit": "°C"})
                        if i < len(temp_max) and temp_max[i] is not None:
                            records.append({**base, "indicator": "Daily max temperature", "value": float(temp_max[i]), "unit": "°C"})
                        if i < len(temp_min) and temp_min[i] is not None:
                            records.append({**base, "indicator": "Daily min temperature", "value": float(temp_min[i]), "unit": "°C"})
                        if i < len(precip) and precip[i] is not None:
                            records.append({**base, "indicator": "Daily precipitation", "value": float(precip[i]), "unit": "mm"})

                except Exception as exc:
                    logger.warning("Open-Meteo weather failed for %s: %s", region_name, exc)
        logger.info("Open-Meteo weather: collected %d records.", len(records))
        return records

    # ─── Source 2: NASA POWER (satellite-based temp & precipitation) ─────────
    async def _collect_nasa_power(self) -> list[dict[str, Any]]:
        """Monthly temperature & precipitation from NASA POWER API (free, no key)."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for region_name, coords in self.CHAD_REGIONS.items():
                url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
                params = {
                    "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR",
                    "community": "AG",
                    "longitude": coords["lon"],
                    "latitude": coords["lat"],
                    "start": "2020",
                    "end": "2024",
                    "format": "JSON",
                }
                try:
                    res = await client.get(url, params=params)
                    res.raise_for_status()
                    data = res.json()
                    parameters = data.get("properties", {}).get("parameter", {})

                    param_map = {
                        "T2M": ("Monthly mean temperature", "°C"),
                        "T2M_MAX": ("Monthly max temperature", "°C"),
                        "T2M_MIN": ("Monthly min temperature", "°C"),
                        "PRECTOTCORR": ("Monthly precipitation", "mm/day"),
                    }

                    for param_key, (indicator_name, unit) in param_map.items():
                        param_data = parameters.get(param_key, {})
                        for date_key, val in param_data.items():
                            if val is None or val == -999.0:
                                continue
                            # date_key format: "YYYYMM" (e.g., "202301") or "YYYY13" for annual
                            if len(date_key) == 6 and date_key[:4].isdigit():
                                yr = int(date_key[:4])
                                mo = int(date_key[4:6])
                                if mo < 1 or mo > 12:
                                    continue  # Skip annual summaries (month=13)
                                records.append({
                                    "year": yr,
                                    "month": mo,
                                    "day": 1,
                                    "value": float(val),
                                    "source": "NASA POWER",
                                    "indicator": indicator_name,
                                    "unit": unit,
                                    "region": region_name,
                                    "url": url,
                                })
                except Exception as exc:
                    logger.warning("NASA POWER failed for %s: %s", region_name, exc)
        logger.info("NASA POWER: collected %d records.", len(records))
        return records

    # ─── Source 3: NASA FIRMS (active fire / bush fire hotspots) ──────────────
    async def _collect_nasa_firms(self) -> list[dict[str, Any]]:
        """Active fire hotspots in Chad from NASA FIRMS VIIRS (requires MAP_KEY).

        API endpoint: https://firms.modaps.eosdis.nasa.gov/api/country/csv/{MAP_KEY}/{source}/{country}/{day_range}/{date}
        Source: VIIRS_SNPP_NRT
        Country: TCD (Chad, ISO-3)
        """
        map_key = getattr(settings, "nasa_firms_key", None)
        if not map_key:
            logger.warning("NASA FIRMS: nasa_firms_key not configured in .env — skipping fire data collection.")
            return []

        records: list[dict[str, Any]] = []
        # Query active fires in Chad BBOX (west, south, east, north) for the last 5 days
        bbox_str = f"{self.CHAD_BBOX['west']},{self.CHAD_BBOX['south']},{self.CHAD_BBOX['east']},{self.CHAD_BBOX['north']}"
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/{bbox_str}/5"
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                res = await client.get(url)
                res.raise_for_status()
                csv_text = res.text

                reader = csv.DictReader(io.StringIO(csv_text))
                for row in reader:
                    try:
                        lat = float(row.get("latitude", 0))
                        lon = float(row.get("longitude", 0))
                        brightness = float(row.get("bright_ti4", 0) or row.get("brightness", 0))
                        frp = float(row.get("frp", 0))
                        confidence = row.get("confidence", "nominal")
                        acq_date = row.get("acq_date", "")

                        if not acq_date or brightness == 0:
                            continue

                        yr = int(acq_date[:4])
                        mo = int(acq_date[5:7])
                        dy = int(acq_date[8:10])

                        # Determine approximate region from lat/lon
                        region = self._geolocate_region(lat, lon)

                        # Fire brightness temperature (Kelvin)
                        records.append({
                            "year": yr, "month": mo, "day": dy,
                            "value": brightness,
                            "source": "NASA FIRMS VIIRS",
                            "indicator": "Fire brightness temperature",
                            "unit": "K",
                            "region": region,
                            "url": url,
                            "meta": {"lat": lat, "lon": lon, "confidence": confidence},
                        })

                        # Fire Radiative Power (MW)
                        if frp > 0:
                            records.append({
                                "year": yr, "month": mo, "day": dy,
                                "value": frp,
                                "source": "NASA FIRMS VIIRS",
                                "indicator": "Fire radiative power",
                                "unit": "MW",
                                "region": region,
                                "url": url,
                                "meta": {"lat": lat, "lon": lon, "confidence": confidence},
                            })

                    except (ValueError, KeyError) as exc:
                        logger.debug("Skipping FIRMS row: %s", exc)
                        continue

            except Exception as exc:
                logger.warning("NASA FIRMS collection failed: %s", exc)

        logger.info("NASA FIRMS: collected %d fire records for Chad.", len(records))
        return records

    def _geolocate_region(self, lat: float, lon: float) -> str:
        """Map a lat/lon to the nearest known Chad region."""
        best_region = "Tchad (autre)"
        best_dist = float("inf")
        for name, coords in self.CHAD_REGIONS.items():
            dist = (lat - coords["lat"]) ** 2 + (lon - coords["lon"]) ** 2
            if dist < best_dist:
                best_dist = dist
                best_region = name
        return best_region

    # ─── Normalize: raw dict → ObservationCreate ─────────────────────────────
    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None

        yr = int(record["year"])
        mo = int(record.get("month", 1))
        dy = int(record.get("day", 1))
        ref_date = date(yr, mo, dy)
        unit_str = str(record.get("unit", "unit"))[:30]

        # Build notes with fire metadata if present
        notes = f"Automated harvest by EnvironmentAgent from {record['source']}."
        meta = record.get("meta")
        if meta:
            notes += f" [lat={meta.get('lat')}, lon={meta.get('lon')}, confidence={meta.get('confidence')}]"

        return ObservationCreate(
            sector="environment",
            indicator=str(record["indicator"]),
            value=float(record["value"]),
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=notes,
        )