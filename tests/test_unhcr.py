import asyncio

import pytest

from app.agents.base import BaseAgent
from app.agents.demography import DemographyAgent
from app.services.storage import ObservationRepository

HOSTED = [   # shape copied from the real api.unhcr.org answer (coa=TCD)
    {"year": 2015, "coo_name": "Central African Rep.", "coo_iso": "CAF", "coa_iso": "TCD",
     "refugees": 63397, "asylum_seekers": 1276, "idps": 0},
    {"year": 2015, "coo_name": "Sudan", "coo_iso": "SDN", "coa_iso": "TCD", "refugees": 300000, "asylum_seekers": "-", "idps": "-"},
    {"year": 2015, "coo_name": "Chad", "coo_iso": "TCD", "coa_iso": "TCD", "refugees": 0, "asylum_seekers": 0, "idps": 51999},
    {"year": 2024, "coo_name": "Sudan", "coo_iso": "SDN", "coa_iso": "TCD", "refugees": 1000000, "asylum_seekers": 5000, "idps": 0},
    {"year": "x", "coo_name": "Nowhere", "coo_iso": "NWH", "coa_iso": "TCD", "refugees": 5},
]
ABROAD = [
    {"year": 2015, "coo_iso": "TCD", "coa_iso": "CMR", "refugees": 100, "asylum_seekers": 2},
    {"year": 2015, "coo_iso": "TCD", "coa_iso": "FRA", "refugees": "-", "asylum_seekers": 8},
    {"year": 2015, "coo_iso": "TCD", "coa_iso": "TCD", "refugees": 7777, "asylum_seekers": 0},     # not abroad
]


def _agent(tmp_path):
    return DemographyAgent(ObservationRepository(database_path=tmp_path / "u.db"))


def _by(records):
    return {(r["year"], r["indicator"]): r["value"] for r in records}


def test_hosted_displaced_and_abroad_are_summed(tmp_path):
    got = _by(_agent(tmp_path).unhcr_records(HOSTED, ABROAD))
    assert got[(2015, "Refugees hosted in Chad")] == 363397          # '-' and the Chad row are not counted
    assert got[(2015, "Asylum seekers in Chad")] == 1276
    assert got[(2015, "Refugees from Sudan in Chad")] == 300000
    assert got[(2015, "Internally displaced persons in Chad")] == 51999
    assert got[(2015, "Chadian refugees abroad")] == 100
    assert got[(2015, "Chadian asylum seekers abroad")] == 10
    assert got[(2024, "Refugees hosted in Chad")] == 1_000_000


def test_zero_and_dash_produce_no_row_and_bad_years_are_skipped(tmp_path):
    records = _agent(tmp_path).unhcr_records(HOSTED, ABROAD)
    assert not any(r["indicator"] == "Refugees from Chad in Chad" for r in records)
    assert all(r["value"] > 0 for r in records)
    assert {r["year"] for r in records} == {2015, 2024}


def test_records_normalise_with_the_unhcr_licence_and_attribution(tmp_path):
    agent = _agent(tmp_path)
    obs = [agent.normalize(r) for r in agent.unhcr_records(HOSTED, ABROAD)]
    assert all(o and o.sector == "demography" and o.license == "CC BY 4.0" and o.source == "UNHCR" for o in obs)
    assert all("UNHCR Refugee Population Statistics Database" in o.notes and "terms-use-datasets" in o.notes for o in obs)
    assert {o.reference_date.isoformat() for o in obs} == {"2015-12-31", "2024-12-31"}


def test_collect_pages_and_asks_for_both_directions(monkeypatch, tmp_path):
    asked = []

    async def fake_fetch(client, url, params=None, **kw):
        asked.append(dict(params))
        if params.get("coa") == "TCD":
            return {"maxPages": 2, "items": HOSTED[:2] if params["page"] == 1 else HOSTED[2:4]}
        return {"maxPages": 1, "items": ABROAD}
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    records = asyncio.run(_agent(tmp_path).collect("unhcr"))
    assert [a.get("page") for a in asked if a.get("coa")] == [1, 2]           # followed maxPages
    assert any(a.get("coo") == "TCD" and a.get("coa_all") == "true" for a in asked)
    assert all(a["cf_type"] == "ISO" and a["yearFrom"] == 2000 for a in asked)
    assert _by(records)[(2024, "Refugees hosted in Chad")] == 1_000_000


def test_a_broken_answer_gives_no_rows_not_a_crash(monkeypatch, tmp_path):
    async def fake_fetch(client, url, params=None, **kw):
        return None
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    assert asyncio.run(_agent(tmp_path).collect("unhcr")) == []


def test_unknown_source_still_raises(tmp_path):
    with pytest.raises(ValueError, match="unhcr"):
        asyncio.run(_agent(tmp_path).collect("nope"))
