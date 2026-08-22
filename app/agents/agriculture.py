from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class AgricultureAgent(BaseAgent):
    sector = "agriculture"
    name = "AgricultureAgent"

    # World Bank & FAO-aligned indicators relevant to Chad's agricultural sector
    WORLD_BANK_INDICATORS = {
        "AG.PRD.CREL.MT": ("Cereal total production", "metric tons"),
        "AG.YLD.CREL.KG": ("Cereal yield", "kg per hectare"),
        "AG.PRD.CROP.XD": ("Crop production index", "index (2014-2016 = 100)"),
        "AG.PRD.FOOD.XD": ("Food production index", "index (2014-2016 = 100)"),
        "AG.PRD.LVST.XD": ("Livestock production index", "index (2014-2016 = 100)"),
        "AG.LND.AGRI.K2": ("Agricultural land area", "sq. km"),
        "AG.LND.ARBL.ZS": ("Arable land percentage", "% of land area"),
        "AG.CON.FERT.ZS": ("Fertilizer consumption", "kg/ha (arable land)"),
        "NV.AGR.TOTL.ZS": ("Agriculture value added", "% of GDP"),
        "SL.AGR.EMPL.ZS": ("Employment in agriculture", "% of total employment"),
        "SP.RUR.TOTL.ZS": ("Rural population", "% of total population"),
    }

    # Key agricultural regions in Chad with GPS coordinates for agrometeorology
    CHAD_AGRICULTURAL_REGIONS = {
        "Moundou (Logone Occidental)": {"lat": 8.56, "lon": 16.08, "zone": "Sud - Zone vivrière et cotonnier"},
        "Sarh (Moyen-Chari)": {"lat": 9.15, "lon": 18.39, "zone": "Sud-Est - Zone agricole humide"},
        "N'Djamena (Chari-Baguirmi)": {"lat": 12.11, "lon": 15.05, "zone": "Centre - Zone maraîchère et fluviatile"},
        "Abéché (Ouaddaï)": {"lat": 13.82, "lon": 20.83, "zone": "Est - Zone agropastorale sahelienne"},
    }

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "open-meteo":
            return await self._collect_open_meteo()

        if source == "nasa-power-agro":
            return await self._collect_nasa_power_agro()

        if source in ("all", "auto"):
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_open_meteo(),
                self._collect_nasa_power_agro(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for res in results:
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("Collection source failed during 'all' run: %s", res)
            return combined

        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'open-meteo', 'nasa-power-agro', 'demo'.")

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2020,
                "value": 118.2,
                "source": "FreeDatatd demo",
                "indicator": "Crop production index",
                "unit": "index (2014-2016 = 100)",
                "region": "national",
            },
            {
                "year": 2021,
                "value": 121.7,
                "source": "FreeDatatd demo",
                "indicator": "Crop production index",
                "unit": "index (2014-2016 = 100)",
                "region": "national",
            },
            {
                "year": 2022,
                "value": 124.4,
                "source": "FreeDatatd demo",
                "indicator": "Crop production index",
                "unit": "index (2014-2016 = 100)",
                "region": "national",
            },
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/TD/indicator/{code}"
                params = {"format": "json", "per_page": 100, "date": "2000:2025"}
                try:
                    res = await client.get(url, params=params)
                    res.raise_for_status()
                    payload = res.json()
                    if isinstance(payload, list) and len(payload) >= 2 and payload[1]:
                        for item in payload[1]:
                            val = item.get("value")
                            date_str = item.get("date", "")
                            if val is not None and date_str.isdigit():
                                records.append(
                                    {
                                        "year": int(date_str),
                                        "value": float(val),
                                        "source": "World Bank",
                                        "indicator": name,
                                        "unit": unit,
                                        "region": "national",
                                        "url": url,
                                    }
                                )
                except Exception as exc:
                    logger.warning("Failed to collect World Bank indicator %s: %s", code, exc)
        return records

    async def _collect_open_meteo(self) -> list[dict[str, Any]]:
        """Collect real soil moisture, FAO evapotranspiration & crop stress indicators for Chad regions."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for region_name, coords in self.CHAD_AGRICULTURAL_REGIONS.items():
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": coords["lat"],
                    "longitude": coords["lon"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-06-30",
                    "daily": "et0_fao_evapotranspiration,soil_moisture_0_to_7cm_mean,soil_moisture_7_to_28cm_mean,vapor_pressure_deficit_max,shortwave_radiation_sum,precipitation_sum,temperature_2m_mean",
                    "timezone": "Africa/Ndjamena",
                }
                try:
                    res = await client.get(url, params=params)
                    res.raise_for_status()
                    data = res.json().get("daily", {})
                    dates = data.get("time", [])
                    et0 = data.get("et0_fao_evapotranspiration", [])
                    sm07 = data.get("soil_moisture_0_to_7cm_mean", [])
                    sm728 = data.get("soil_moisture_7_to_28cm_mean", [])
                    vpd = data.get("vapor_pressure_deficit_max", [])
                    rad = data.get("shortwave_radiation_sum", [])
                    precip = data.get("precipitation_sum", [])
                    temp = data.get("temperature_2m_mean", [])

                    for i, dt_str in enumerate(dates):
                        yr, mo, dy = int(dt_str[:4]), int(dt_str[5:7]), int(dt_str[8:10])
                        base = {
                            "year": yr, "month": mo, "day": dy,
                            "source": "Open-Meteo Agro-Climate",
                            "region": region_name,
                            "url": url,
                        }

                        if i < len(sm07) and sm07[i] is not None:
                            records.append({**base, "indicator": "Topsoil moisture (0-7cm)", "value": float(sm07[i]), "unit": "m³/m³"})
                        if i < len(sm728) and sm728[i] is not None:
                            records.append({**base, "indicator": "Root zone soil moisture (7-28cm)", "value": float(sm728[i]), "unit": "m³/m³"})
                        if i < len(vpd) and vpd[i] is not None:
                            records.append({**base, "indicator": "Vapour pressure deficit (VPD max)", "value": float(vpd[i]), "unit": "kPa"})
                        if i < len(et0) and et0[i] is not None:
                            records.append({**base, "indicator": "FAO-56 Reference Evapotranspiration (ET0)", "value": float(et0[i]), "unit": "mm/day"})
                        if i < len(rad) and rad[i] is not None:
                            records.append({**base, "indicator": "Solar radiation flux", "value": float(rad[i]), "unit": "MJ/m²"})
                        if i < len(precip) and precip[i] is not None and precip[i] > 0:
                            records.append({**base, "indicator": "Daily rainfall", "value": float(precip[i]), "unit": "mm"})
                        if i < len(temp) and temp[i] is not None:
                            records.append({**base, "indicator": "Daily mean temperature", "value": float(temp[i]), "unit": "°C"})
                except Exception as exc:
                    logger.warning("Failed to collect Open-Meteo agro data for %s: %s", region_name, exc)
        return records

    async def _collect_nasa_power_agro(self) -> list[dict[str, Any]]:
        """Collect Photosynthetically Active Radiation (PAR) & root-zone soil wetness from NASA POWER AG API."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for region_name, coords in self.CHAD_AGRICULTURAL_REGIONS.items():
                url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
                params = {
                    "parameters": "ALLSKY_SFC_PAR_TOT,GWETROOT,GWETTOP",
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
                    parameters = res.json().get("properties", {}).get("parameter", {})

                    param_map = {
                        "ALLSKY_SFC_PAR_TOT": ("Photosynthetically Active Radiation (PAR)", "W/m²"),
                        "GWETROOT": ("Root zone soil wetness index", "ratio (0-1)"),
                        "GWETTOP": ("Surface soil wetness index", "ratio (0-1)"),
                    }

                    for param_key, (ind_name, unit_name) in param_map.items():
                        data_dict = parameters.get(param_key, {})
                        for date_key, val in data_dict.items():
                            if val is None or val == -999.0:
                                continue
                            if len(date_key) == 6 and date_key[:4].isdigit():
                                yr = int(date_key[:4])
                                mo = int(date_key[4:6])
                                if mo < 1 or mo > 12:
                                    continue
                                records.append({
                                    "year": yr, "month": mo, "day": 1,
                                    "value": float(val),
                                    "source": "NASA POWER Agro",
                                    "indicator": ind_name,
                                    "unit": unit_name,
                                    "region": region_name,
                                    "url": url,
                                })
                except Exception as exc:
                    logger.warning("Failed to collect NASA POWER agro metrics for %s: %s", region_name, exc)
        return records



    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None

        yr = int(record["year"])
        mo = int(record.get("month", 1))
        dy = int(record.get("day", 1))
        ref_date = date(yr, mo, dy)
        unit_str = str(record.get("unit", "unit"))[:30]

        return ObservationCreate(
            sector="agriculture",
            indicator=str(record["indicator"]),
            value=float(record["value"]),
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"]),
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by AgricultureAgent from {record['source']}.",
        )
