from __future__ import annotations

from typing import Any
import asyncio
import logging

import httpx

from app.agents.pink_sheet import PAGE_URL, find_workbook_url, parse_pink_sheet
from app.agents.wb_sector import WorldBankSectorAgent

logger = logging.getLogger(__name__)


class TradeAgent(WorldBankSectorAgent):
    """Foreign trade of Chad: composition and value of exports and imports (World Bank).
    Exports and imports as a share of GDP, foreign investment and tariffs stay in MarketsAgent; logistics in TransportAgent."""

    sector = "trade"
    name = "TradeAgent"

    WORLD_BANK_INDICATORS = {
        "TX.VAL.MRCH.CD.WT": ("Merchandise exports", "USD"),
        "TM.VAL.MRCH.CD.WT": ("Merchandise imports", "USD"),
        "TG.VAL.TOTL.GD.ZS": ("Merchandise trade", "% of GDP"),
        "TX.VAL.FUEL.ZS.UN": ("Fuel exports", "% of merchandise exports"),
        "TX.VAL.FOOD.ZS.UN": ("Food exports", "% of merchandise exports"),
        "TX.VAL.AGRI.ZS.UN": ("Agricultural raw materials exports", "% of merchandise exports"),
        "TX.VAL.MMTL.ZS.UN": ("Ores and metals exports", "% of merchandise exports"),
        "TM.VAL.FOOD.ZS.UN": ("Food imports", "% of merchandise imports"),
        "TM.VAL.FUEL.ZS.UN": ("Fuel imports", "% of merchandise imports"),
        "TM.VAL.AGRI.ZS.UN": ("Agricultural raw materials imports", "% of merchandise imports"),
        "TT.PRI.MRCH.XD.WD": ("Net barter terms of trade index", "index (2015 = 100)"),
    }
    DEMO = ("Merchandise exports", "USD", 3.1e9)

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "pink-sheet":
            return await self._collect_pink_sheet()
        if source in ("all", "auto"):
            names = ("world-bank", "pink-sheet")
            results = await asyncio.gather(self._collect_world_bank(), self._collect_pink_sheet(), return_exceptions=True)
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("TradeAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined
        try:
            return await super().collect(source)
        except ValueError as exc:
            raise ValueError(str(exc).replace("'world-bank', 'demo'", "'world-bank', 'pink-sheet', 'demo'")) from exc

    async def _collect_pink_sheet(self) -> list[dict[str, Any]]:
        """World commodity prices (monthly, since 2000): the workbook link is read from the World Bank page."""
        headers = {"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedata-td.onrender.com)"}
        async with httpx.AsyncClient(timeout=90, follow_redirects=True, headers=headers) as client:
            try:
                page = await client.get(PAGE_URL)
                page.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"World Bank commodity page not reachable ({exc})") from exc
            url = find_workbook_url(page.text)
            if not url:
                raise RuntimeError("Pink Sheet: the workbook link was not found on the World Bank page")
            last: Exception | None = None
            for attempt in (1, 2, 3):
                try:
                    reply = await client.get(url)
                    reply.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    last = exc
                    await asyncio.sleep(2 * attempt)
            else:
                raise RuntimeError(f"Pink Sheet workbook download failed ({last})")
        try:
            records = parse_pink_sheet(reply.content, url=url)
        except Exception as exc:
            raise RuntimeError(f"Pink Sheet workbook not readable ({exc})") from exc
        if not records:
            raise RuntimeError("Pink Sheet: no price found in the workbook")
        return records
