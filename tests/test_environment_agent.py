import pytest
from app.agents.environment import EnvironmentAgent
from app.services.storage import ObservationRepository

@pytest.mark.anyio
async def test_environment_agent_normalize():
    repo = ObservationRepository()
    agent = EnvironmentAgent(repo)
    
    raw_sample = {
        "year": 2024,
        "month": 8,
        "day": 22,
        "value": 315.5,
        "source": "NASA FIRMS VIIRS",
        "indicator": "Fire brightness temperature",
        "unit": "K",
        "region": "Sarh (Moyen-Chari)",
        "url": "https://firms.modaps.eosdis.nasa.gov",
        "meta": {"lat": 9.15, "lon": 18.39, "confidence": "high"}
    }
    
    obs = agent.normalize(raw_sample)
    assert obs is not None
    assert obs.sector == "environment"
    assert obs.indicator == "Fire brightness temperature"
    assert obs.value == 315.5
    assert obs.unit == "K"
    assert "lat=9.15" in (obs.notes or "")
