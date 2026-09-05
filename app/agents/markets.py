from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class MarketsAgent(BaseAgent):
    """Collects market, trade & price data for Chad from 4 major international open data sources:
    1. World Bank (Trade, Inflation, FDI, Tariffs, Financial Inclusion)
    2. WFP VAM (World Food Programme Vulnerability Analysis & Mapping Market Prices)
    3. HDX / UN OCHA (Humanitarian Data Exchange Chad Market Datasets)
    4. FAOSTAT Market (FAO Commodity & Food Price Index)
    """

    sector = "markets"
    name = "MarketsAgent"

    # 1. World Bank Indicators
    WORLD_BANK_INDICATORS = {
        "NE.TRD.GNFS.ZS": ("Trade volume", "% of GDP"),
        "NE.EXP.GNFS.ZS": ("Exports of goods and services", "% of GDP"),
        "NE.IMP.GNFS.ZS": ("Imports of goods and services", "% of GDP"),
        "BX.KLT.DINV.WD.GD.ZS": ("Foreign direct investment net inflows", "% of GDP"),
        "TM.TAX.MRCH.WM.AR.ZS": ("Mean tariff rate on imports", "%"),
        "FP.CPI.TOTL.ZG": ("Consumer price inflation", "% annual"),
        "FP.CPI.TOTL": ("Consumer price index", "index (2010=100)"),
        "FX.OWN.TOTL.ZS": ("Account ownership at financial institution", "% age 15+"),
    }

    # ISO3 for Chad
    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "wfp":
            return await self._collect_wfp_prices()

        if source == "hdx":
            return await self._collect_hdx_ocha()

        if source == "faostat":
            return await self._collect_faostat_prices()

        if source in ("all", "auto"):
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_wfp_prices(),
                self._collect_hdx_ocha(),
                self._collect_faostat_prices(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for res in results:
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("MarketsAgent source failed: %s", res)
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'wfp', 'hdx', 'faostat', 'demo'."
        )

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 52.3,
                "source": "World Bank",
                "indicator": "Trade volume",
                "unit": "% of GDP",
                "region": "national",
            },
            {
                "year": 2024,
                "value": 450.0,
                "source": "WFP VAM",
                "indicator": "Sorghum market price",
                "unit": "XAF/kg",
                "region": "N'Djamena (Chari-Baguirmi)",
            },
            {
                "year": 2024,
                "value": 380.0,
                "source": "HDX / UN OCHA",
                "indicator": "Maize local price",
                "unit": "XAF/kg",
                "region": "Moundou (Logone Occidental)",
            },
            {
                "year": 2023,
                "value": 124.5,
                "source": "FAOSTAT Market",
                "indicator": "Global Food Price Index",
                "unit": "index (2014-2016=100)",
                "region": "national",
            },
        ]

    # ─── Source 1: World Bank ────────────────────────────────────────────────
    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        """Fetch trade, inflation & market indicators from World Bank API."""
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

    # ─── Source 2: WFP VAM Market Prices ─────────────────────────────────────
    async def _collect_wfp_prices(self) -> list[dict[str, Any]]:
        """Fetch commodity food prices for Chad from WFP VAM API."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Get Chad's WFP country adm0code
                countries_url = "https://api.vam.wfp.org/geodata/CountriesInRegion"
                res = await client.get(countries_url, params={"region": "WCA"})
                res.raise_for_status()
                countries = res.json()

                chad_id = None
                if isinstance(countries, list):
                    for c in countries:
                        if c.get("iso3") == self.CHAD_ISO3 or c.get("adm0_name", "").lower() == "chad":
                            chad_id = c.get("adm0_code")
                            break

                if not chad_id:
                    return await self._collect_wfp_direct(client)

                prices_url = "https://api.vam.wfp.org/MarketPrices/PriceMonthly"
                params = {"adm0Code": chad_id, "startDate": "2023-01-01", "endDate": "2024-12-31"}
                res = await client.get(prices_url, params=params)
                res.raise_for_status()
                data = res.json()

                if isinstance(data, list):
                    for item in data:
                        commodity = item.get("commodityName", "Unknown commodity")
                        price = item.get("commodityPriceFlag") or item.get("commodityPrice")
                        market = item.get("marketName", "national")
                        unit_name = item.get("commodityUnitName", "XAF/kg")
                        price_date = item.get("commodityPriceDate", "")

                        if price is None:
                            continue

                        yr = int(price_date[:4]) if price_date and len(price_date) >= 4 else 2024
                        mo = int(price_date[5:7]) if price_date and len(price_date) >= 7 else 1

                        records.append({
                            "year": yr,
                            "month": mo,
                            "day": 1,
                            "value": round(float(price), 2),
                            "source": "WFP VAM",
                            "indicator": f"{commodity} price",
                            "unit": unit_name,
                            "region": market,
                            "url": prices_url,
                        })
            except Exception as exc:
                logger.warning("WFP market prices collection failed: %s", exc)
        return records

    async def _collect_wfp_direct(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        """Fallback: try WFP direct endpoint for Chad food prices."""
        records: list[dict[str, Any]] = []
        try:
            url = "https://api.vam.wfp.org/MarketPrices/PriceMonthly"
            res = await client.get(url, params={"iso3": self.CHAD_ISO3, "startDate": "2023-01-01"})
            res.raise_for_status()
            data = res.json()
            if isinstance(data, list):
                for item in data[:200]:
                    commodity = item.get("commodityName", "Commodity")
                    price = item.get("commodityPrice")
                    if price is None:
                        continue
                    records.append({
                        "year": 2024,
                        "value": round(float(price), 2),
                        "source": "WFP VAM",
                        "indicator": f"{commodity} price",
                        "unit": "XAF/kg",
                        "region": item.get("marketName", "national"),
                        "url": url,
                    })
        except Exception as exc:
            logger.warning("WFP direct endpoint failed: %s", exc)
        return records

    # ─── Source 3: HDX / UN OCHA Chad Market Dataset ────────────────────────
    async def _collect_hdx_ocha(self) -> list[dict[str, Any]]:
        """Fetch metadata & market datasets for Chad from UN OCHA HDX (Humanitarian Data Exchange)."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = "https://data.humdata.org/api/3/action/package_show"
            params = {"id": "wfp-food-prices-for-chad"}
            try:
                res = await client.get(url, params=params)
                res.raise_for_status()
                payload = res.json()
                result = payload.get("result", {})
                num_resources = len(result.get("resources", []))

                if num_resources > 0:
                    records.append({
                        "year": 2024,
                        "value": float(num_resources),
                        "source": "HDX / UN OCHA",
                        "indicator": "Active market price datasets",
                        "unit": "datasets",
                        "region": "national",
                        "url": url,
                    })
            except Exception as exc:
                logger.warning("HDX / UN OCHA collection failed: %s", exc)

        return records

    # ─── Source 4: FAOSTAT Market & Food Price Index ────────────────────────
    async def _collect_faostat_prices(self) -> list[dict[str, Any]]:
        """Fetch Food Price Index & trade metrics from FAOSTAT Market API."""
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            url = "https://fenixservices.fao.org/faostat/api/v1/en/data/CP"
            params = {"area": "39", "show_codes": "true", "show_unit": "true"}  # Area 39 = Chad
            try:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    for item in data[:50]:
                        val = item.get("Value")
                        yr = item.get("Year")
                        ind = item.get("Item", "Consumer Price Index")
                        unit = item.get("Unit", "index")
                        if val is not None and yr:
                            records.append({
                                "year": int(yr),
                                "value": round(float(val), 2),
                                "source": "FAOSTAT Market",
                                "indicator": f"{ind} price index",
                                "unit": unit,
                                "region": "national",
                                "url": url,
                            })
            except Exception as exc:
                logger.warning("FAOSTAT Market collection failed: %s", exc)

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

        return ObservationCreate(
            sector="markets",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license="CC BY 4.0",
            notes=f"Automated harvest by MarketsAgent from {record['source']}.",
        )
