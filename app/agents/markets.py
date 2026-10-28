from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
import logging
from typing import Any

import httpx

from app.agents.base import BaseAgent, source_terms, wb_years
from app.agents.wfp_prices import HDX_PACKAGE_ID, HDX_PACKAGE_URL, parse_wfp_csv, pick_csv_url
from app.agents.fews_prices import FEWS_URL, extract_items, parse_record, resolve_collisions
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class MarketsAgent(BaseAgent):
    """Collects market, trade & price data for Chad:
    1. World Bank (Trade, Inflation, FDI, Tariffs, Financial Inclusion), annual national series
    2. FEWS NET (retail prices of staple foods by market, monthly or weekly)
    3. WFP VAM market prices (legacy endpoint, kept as an optional extra source)
    4. FAOSTAT Market (FAO consumer price index)
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

        if source in ("fews", "fews-net"):
            return await self._collect_fews_prices()

        if source == "faostat":
            return await self._collect_faostat_prices()

        if source in ("all", "auto"):
            names = ("world-bank", "fews-net", "wfp", "faostat")
            results = await asyncio.gather(
                self._collect_world_bank(),
                self._collect_fews_prices(),
                self._collect_wfp_prices(),
                self._collect_faostat_prices(),
                return_exceptions=True,
            )
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("MarketsAgent source %s failed: %s", name, res)
                    self.source_errors.append(f"{name}: {res}")
            return combined

        raise ValueError(
            f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'fews-net', 'wfp', 'faostat', 'demo'."
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

    # ─── Source 2: WFP market prices (CSV published on HDX) ──────────────────
    WFP_HISTORY_YEARS = 3

    async def _collect_wfp_prices(self) -> list[dict[str, Any]]:
        """Monthly retail prices by market and product from the WFP file on HDX.

        Raises when the HDX catalogue or the file cannot be read, so the failure shows up in the
        run result."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0), follow_redirects=True) as client:
            reason: list[str] = []
            package = await self.fetch_json_with_retry(
                client, HDX_PACKAGE_URL, params={"id": HDX_PACKAGE_ID}, errors=reason)
            if package is None:
                raise RuntimeError(f"HDX catalogue did not answer ({reason[0] if reason else 'no detail'})")
            csv_url = pick_csv_url(package)
            if not csv_url:
                raise RuntimeError("HDX: no CSV file found in the WFP Chad food prices dataset")
            text = await self.fetch_text_with_retry(client, csv_url, throttle_seconds=0.3)
            if not text:
                raise RuntimeError("HDX: the WFP price file could not be downloaded")
        records, skipped = parse_wfp_csv(text, self.WFP_HISTORY_YEARS)
        if not records:
            raise RuntimeError("WFP price file read but no usable retail XAF price found")
        if skipped:
            logger.info("WFP prices: %d row(s) skipped (duplicates, other currency, bad value).", skipped)
        return records

    # ─── Source 2b: FEWS NET market prices ───────────────────────────────────
    # Two calendar years back is ~15 000 price rows (all products, all markets): enough for
    # trends, and a response a free-tier server can download and hold in memory.
    FEWS_HISTORY_YEARS = 2
    FEWS_MAX_PAGES = 200

    async def _collect_fews_prices(self) -> list[dict[str, Any]]:
        """Retail prices of staple foods by market for the last FEWS_HISTORY_YEARS years.

        Raises when the API cannot be reached or answers with an unreadable shape, so the
        failure is reported in the run result instead of looking like "no new prices"."""
        start = f"{datetime.now(UTC).year - self.FEWS_HISTORY_YEARS}-01-01"
        params: dict[str, Any] | None = {"country_code": "TD", "format": "json", "start_date": start}
        url: str | None = FEWS_URL
        records: list[dict[str, Any]] = []
        skipped = 0
        # A large JSON answer can take a while to build on their side: patient read timeout.
        timeout = httpx.Timeout(240.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for _ in range(self.FEWS_MAX_PAGES):
                reason: list[str] = []
                payload = await self.fetch_json_with_retry(
                    client, url, params=params, throttle_seconds=0.3, errors=reason)
                if payload is None:
                    raise RuntimeError(f"FEWS NET did not answer ({reason[0] if reason else 'no detail'})")
                items, url = extract_items(payload)
                for item in items:
                    parsed = parse_record(item)
                    if parsed is None:
                        skipped += 1
                    else:
                        records.append(parsed)
                params = None            # the "next" URL already carries its query string
                if not url:
                    break
        if skipped:
            logger.info("FEWS NET: %d row(s) ignored (no price, date or product).", skipped)
        records, renamed, dropped = resolve_collisions(records)
        if renamed or dropped:
            logger.info("FEWS NET: %d row(s) told apart by unit, %d duplicate(s) dropped.", renamed, dropped)
        logger.info("FEWS NET: collected %d price records.", len(records))
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

        default_licence, default_notes = source_terms(str(record["source"]), "MarketsAgent")
        return ObservationCreate(
            sector="markets",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license=str(record.get("license") or default_licence)[:50],
            notes=(f"Automated harvest by MarketsAgent from {record['source']}. {record['attribution']}"
                   if record.get("attribution") else default_notes),
        )
