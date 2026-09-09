import asyncio
from pathlib import Path

from app.agents import HealthAgent
from app.services.storage import ObservationRepository


def test_demo_collection_is_stored(tmp_path: Path) -> None:
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    result = asyncio.run(HealthAgent(repository).run("demo"))
    rows = repository.list_observations(sector="health")
    assert result.received == 3
    assert result.stored == 3
    assert len(rows) == 3
    assert rows[0]["country_code"] == "TCD"


def test_unknown_source_raises() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        repository = ObservationRepository(database_path=Path(tmp) / "test.db")
        agent = HealthAgent(repository)
        try:
            asyncio.run(agent.collect("not-a-real-source"))
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "Unknown source" in str(exc)
