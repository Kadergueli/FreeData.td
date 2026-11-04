import asyncio

from app.agents.base import BaseAgent
from app.agents.demography import DemographyAgent
from app.agents.health import HealthAgent
from app.services.storage import ObservationRepository

WB = HealthAgent.WORLD_BANK_INDICATORS


def test_indicator_table_is_clean():
    names = [name for name, _ in WB.values()]
    assert len(set(names)) == len(names)                         # no two codes share a name
    assert all(len(unit) <= 40 for _, unit in WB.values())       # normalize() would cut it
    assert not set(WB) & set(DemographyAgent.WORLD_BANK_INDICATORS)   # no doubles with demography
    for code in ("SH.IMM.MEAS", "SH.TBS.INCD", "SH.MLR.INCD.P3", "SH.DYN.AIDS.ZS", "SH.DYN.NMRT"):
        assert code in WB


def test_collects_every_series_since_2000_and_skips_empty_years(monkeypatch, tmp_path):
    calls = []

    async def fake_fetch(client, url, params=None, **kw):
        calls.append((url, params))
        return [{"page": 1}, [{"date": "2023", "value": 41.567}, {"date": "2022", "value": None}, {"date": "x", "value": 1}]]
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    agent = HealthAgent(ObservationRepository(database_path=tmp_path / "h.db"))
    records = asyncio.run(agent.collect("world-bank"))
    assert len(calls) == len(WB) and len(records) == len(WB)
    assert all(p["date"].startswith("2000:") for _, p in calls)
    obs = [agent.normalize(r) for r in records]
    assert all(o and o.sector == "health" and o.region == "national" and o.license == "CC BY 4.0" for o in obs)
    assert {o.unit for o in obs} <= {unit[:40] for _, unit in WB.values()}
