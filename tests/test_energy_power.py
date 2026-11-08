import asyncio

from app.agents.energy import EnergyAgent, parse_power_energy
from app.services.storage import ObservationRepository

PARAMS = EnergyAgent.POWER_PARAMETERS
PAYLOAD = {"properties": {"parameter": {
    "ALLSKY_SFC_SW_DWN": {"202401": 6.01, "202402": -999.0, "202413": 6.2, "2024": 5.0},
    "WS50M": {"202401": 4.3, "202413": 4.0},
}}}


def test_parse_keeps_months_only_and_drops_gaps():
    recs = parse_power_energy(PAYLOAD, "Abéché (Ouaddaï)", PARAMS, "u")
    assert [(r["indicator"], r["year"], r["month"], r["value"]) for r in recs] == [
        ("Solar irradiance (all-sky)", 2024, 1, 6.01), ("Wind speed at 50 m", 2024, 1, 4.3)]
    assert parse_power_energy({}, "r", PARAMS, "u") == [] and parse_power_energy(None, "r", PARAMS, "u") == []


def test_collect_reports_empty_regions_and_normalizes_month(monkeypatch, tmp_path):
    async def fake_fetch(client, url, params=None, **kw):
        return PAYLOAD if params["latitude"] > 12 else None

    monkeypatch.setattr(EnergyAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    agent = EnergyAgent(ObservationRepository(database_path=tmp_path / "e.db"))
    recs = asyncio.run(agent._collect_nasa_power())
    assert recs and agent.source_errors and agent.source_errors[0].startswith("NASA POWER: ")
    obs = agent.normalize(recs[0])
    assert obs.reference_date.month == 1 and obs.region and obs.unit == "kWh/m²/day"
