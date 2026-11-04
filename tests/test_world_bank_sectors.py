"""Every World Bank table: clean names/units, no code shared between sectors, windows reach back to 2000."""
import asyncio

import pytest

from app.agents import (AgricultureAgent, DemographyAgent, EconomyAgent, EducationAgent, HealthAgent)
from app.agents.base import BaseAgent
from app.services.storage import ObservationRepository

AGENTS = [AgricultureAgent, DemographyAgent, EconomyAgent, EducationAgent, HealthAgent]


def test_no_code_or_name_is_shared_between_sectors():
    codes, names = [], []
    for cls in AGENTS:
        for code, (name, unit) in cls.WORLD_BANK_INDICATORS.items():
            codes.append(code); names.append(name.lower())
            assert len(unit) <= 40, (code, unit)
    assert len(set(codes)) == len(codes)
    assert len(set(names)) == len(names)


def test_new_series_are_where_they_belong():
    assert "SI.POV.GINI" in EconomyAgent.WORLD_BANK_INDICATORS
    assert "IT.NET.USER.ZS" in EconomyAgent.WORLD_BANK_INDICATORS
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
