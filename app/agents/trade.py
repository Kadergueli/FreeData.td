from __future__ import annotations

from app.agents.wb_sector import WorldBankSectorAgent


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
