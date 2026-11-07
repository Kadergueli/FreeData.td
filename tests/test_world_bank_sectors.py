"""Every World Bank table: clean names/units, no code shared between sectors, windows reach back to 2000."""
import asyncio

import pytest

from app.agents import (AgricultureAgent, DemographyAgent, EconomyAgent, EducationAgent, EnergyAgent, HealthAgent,
                        MarketsAgent, TelecomAgent, TradeAgent, TransportAgent)
from app.agents.base import BaseAgent
from app.services.storage import ObservationRepository

AGENTS = [AgricultureAgent, DemographyAgent, EconomyAgent, EducationAgent, EnergyAgent, HealthAgent,
          MarketsAgent, TelecomAgent, TradeAgent, TransportAgent]
# Inflation has been collected twice for a long time (economy and markets, under two names); known, not new.
KNOWN_OVERLAP = {"FP.CPI.TOTL.ZG"}


def test_no_code_or_name_is_shared_between_sectors():
    codes, names = [], []
    for cls in AGENTS:
        for code, (name, unit) in getattr(cls, "WORLD_BANK_INDICATORS", {}).items():
            codes.append(code); names.append(name.lower())
            assert len(unit) <= 40, (code, unit)
    shared = {c for c in codes if codes.count(c) > 1}
    assert shared <= KNOWN_OVERLAP, shared
    dup_names = {n for n in names if names.count(n) > 1}
    assert not dup_names, dup_names


def test_new_series_are_where_they_belong():
    assert "SI.POV.GINI" in EconomyAgent.WORLD_BANK_INDICATORS
    assert "IT.NET.USER.ZS" in TelecomAgent.WORLD_BANK_INDICATORS
    assert "IT.NET.USER.ZS" not in EconomyAgent.WORLD_BANK_INDICATORS
    assert "AG.LND.FRST.ZS" in AgricultureAgent.WORLD_BANK_INDICATORS
    assert "SE.ADT.LITR.FE.ZS" in EducationAgent.WORLD_BANK_INDICATORS
    assert "SM.POP.TOTL.ZS" in DemographyAgent.WORLD_BANK_INDICATORS
    assert "SP.DYN.CONU.ZS" in HealthAgent.WORLD_BANK_INDICATORS


@pytest.mark.parametrize("cls", [EconomyAgent, AgricultureAgent])
def test_history_starts_in_2000(monkeypatch, tmp_path, cls):
    seen = []

    async def fake_fetch(client, url, params=None, **kw):
        seen.append(params)
        return [{"page": 1}, [{"date": "2022", "value": 12.345}]]
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    agent = cls(ObservationRepository(database_path=tmp_path / "w.db"))
    records = asyncio.run(agent.collect("world-bank"))
    assert len(seen) == len(cls.WORLD_BANK_INDICATORS) and len(records) == len(seen)
    assert all(p["date"].startswith("2000:") and p["per_page"] >= 100 for p in seen)


def test_telecom_collects_its_table_and_stores_under_its_own_sector(monkeypatch, tmp_path):
    seen = []

    async def fake_fetch(client, url, params=None, **kw):
        seen.append(url)
        return [{"page": 1}, [{"date": "2023", "value": 54.321}, {"date": "2022", "value": None}]]
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    result = asyncio.run(TelecomAgent(repo).run("world-bank"))
    rows = repo.list_observations(sector="telecom", limit=500)
    assert len(seen) == len(TelecomAgent.WORLD_BANK_INDICATORS) and result.stored == len(seen)
    assert {r["sector"] for r in rows} == {"telecom"} and rows[0]["license"] == "CC BY 4.0"


def test_telecom_demo_and_unknown_source(tmp_path):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    assert asyncio.run(TelecomAgent(repo).run("demo")).stored == 1
    with pytest.raises(ValueError, match="Unknown source"):
        asyncio.run(TelecomAgent(repo).collect("nope"))


def test_trade_collects_its_table_and_stores_under_its_own_sector(monkeypatch, tmp_path):
    seen = []

    async def fake_fetch(client, url, params=None, **kw):
        seen.append(url)
        return [{"page": 1}, [{"date": "2022", "value": 3.1e9}, {"date": "2021", "value": None}]]
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    result = asyncio.run(TradeAgent(repo).run("world-bank"))
    rows = repo.list_observations(sector="trade", limit=500)
    assert len(seen) == len(TradeAgent.WORLD_BANK_INDICATORS) and result.stored == len(seen)
    assert {r["sector"] for r in rows} == {"trade"}
