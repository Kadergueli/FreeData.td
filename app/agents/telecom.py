from __future__ import annotations

from app.agents.wb_sector import WorldBankSectorAgent


class TelecomAgent(WorldBankSectorAgent):
    """Telecommunications and digital access for Chad (World Bank, sourced upstream from the ITU)."""

    sector = "telecom"
    name = "TelecomAgent"

    WORLD_BANK_INDICATORS = {
        "IT.NET.USER.ZS": ("Individuals using the Internet", "% of population"),
        "IT.CEL.SETS.P2": ("Mobile cellular subscriptions", "per 100 people"),
        "IT.CEL.SETS": ("Mobile cellular subscriptions, total", "subscriptions"),
        "IT.NET.BBND.P2": ("Fixed broadband subscriptions", "per 100 people"),
        "IT.NET.BBND": ("Fixed broadband subscriptions, total", "subscriptions"),
        "IT.MLT.MAIN.P2": ("Fixed telephone subscriptions", "per 100 people"),
        "IT.NET.SECR.P6": ("Secure Internet servers", "per million people"),
        "BX.GSR.CCIS.ZS": ("ICT service exports", "% of service exports"),
        "TX.VAL.ICTG.ZS.UN": ("ICT goods exports", "% of total goods exports"),
        "TM.VAL.ICTG.ZS.UN": ("ICT goods imports", "% of total goods imports"),
    }
    DEMO = ("Mobile cellular subscriptions", "per 100 people", 54.0)
