import asyncio
from pathlib import Path

from app.agents import AgricultureAgent
from app.services.storage import ObservationRepository


def test_demo_collection_is_stored(tmp_path: Path) -> None:
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    result = asyncio.run(AgricultureAgent(repository).run("demo"))
    rows = repository.list_observations(sector="agriculture")
    assert result.received == 3
    assert result.stored == 3
    assert len(rows) == 3
    assert rows[0]["country_code"] == "TCD"





def test_negative_values_handled_properly(tmp_path: Path) -> None:
    from datetime import date
    from app.schemas import ObservationCreate

    repository = ObservationRepository(database_path=tmp_path / "test.db")
    agent = AgricultureAgent(repository)

    # Temperature below zero or negative GDP growth should be valid
    valid_neg = ObservationCreate(
        sector="agriculture",
        indicator="Mean monthly temperature",
        value=-2.5,
        unit="°C",
        reference_date=date(2024, 1, 1),
        country_code="TCD",
        region="Abéché",
        source="Open-Meteo",
    )
    errors = agent.validate(valid_neg)
    assert errors == []


