"""One spelling per region (the region is part of a row's unique key) and a bounded audit trail."""
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.regions import PROVINCES, canonical_region
from app.schemas import ObservationCreate
from app.services.storage import ObservationRepository


@pytest.mark.parametrize("raw,expected", [
    ("Guéra", "Guera"), ("guera", "Guera"), ("Mayo Kebbi Est", "Mayo-Kebbi Est"),
    ("Chari Baguirmi", "Chari-Baguirmi"), ("Hadjer Lamis", "Hadjer-Lamis"), ("Moyen Chari", "Moyen-Chari"),
    ("Barh El Gazal", "Barh el Gazel"), ("Barh El Gazel", "Barh el Gazel"),
    ("Ouaddaï", "Ouaddai"), ("Tandjilé", "Tandjile"), ("Ndjaména", "N'Djamena"), ("N’Djamena", "N'Djamena"),
    ("Bongor (Mayo Kebbi Est)", "Bongor (Mayo-Kebbi Est)"),
    ("Moussoro (Barh El Gazal)", "Moussoro (Barh el Gazel)"),
    ("Abéché (Ouaddaï)", "Abeche (Ouaddai)"), ("Laï (Tandjilé)", "Lai (Tandjile)"),
    ("Goz Beïda (Sila)", "Goz Beida (Sila)"), ("Mongo (Guéra)", "Mongo (Guera)"),
    ("Dembe (Ndjaména)", "Dembe (N'Djamena)"),
    ("N'djamena (Atrone) (Ndjaména)", "N'Djamena (Atrone) (N'Djamena)"),
    ("N'Djamena (Chari-Baguirmi)", "N'Djamena (N'Djamena)"), ("Ndjamena (Ndjaména)", "N'Djamena (N'Djamena)"),
    ("Oum Hadjer", "Oum Hadjer (Batha)"), ("Oumhadjer (Batha)", "Oum Hadjer (Batha)"),
    ("Amdjarass (Ennedi Est)", "Am-Djarass (Ennedi Est)"),
    ("", "national"), (None, "national"), ("Tout le Tchad", "national"), ("National", "national"),
    ("Atlantis", "Atlantis"),                                  # unknown names are kept
])
def test_canonical_region(raw, expected):
    assert canonical_region(raw) == expected


def test_canonical_region_is_stable():
    for province in PROVINCES:
        assert canonical_region(province) == province
        assert canonical_region(f"Ville ({province})") == f"Ville ({province})"
    for raw in ("Guéra", "Mongo (Guéra)", "Oum Hadjer", "N'djamena (Atrone) (Ndjaména)", "Dembe (Ndjaména)"):
        once = canonical_region(raw)
        assert canonical_region(once) == once


def test_every_write_goes_through_the_unification(tmp_path: Path):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    base = dict(sector="agriculture", indicator="Rain", value=1.0, unit="mm", reference_date="2024-01-01", source="Test")
    obs = [ObservationCreate(**base, region="Guéra"), ObservationCreate(**base, region="Guera")]
    assert obs[0].region == obs[1].region == "Guera"
    repo.upsert_many(obs)
    assert [r["region"] for r in repo.list_observations(limit=10)] == ["Guera"]      # one row, not two


# ---------------------------------------------------------------- audit trail
class _Query:
    def __init__(self, log):
        self.log = log

    def delete(self):
        self.log.append("delete")
        return self

    def lt(self, column, value):
        self.log.append((column, value))
        return self

    def execute(self):
        return None


class _Client:
    def __init__(self):
        self.log = []

    def table(self, name):
        self.log.append(name)
        return _Query(self.log)


def test_purge_old_logs_deletes_only_the_old_lines(tmp_path: Path):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo._supabase = client = _Client()
    assert repo.purge_old_logs() is True
    assert client.log[0] == "table_logs" and "delete" in client.log
    column, cutoff = client.log[-1]
    assert column == "timestamp"
    age = datetime.now(UTC).replace(tzinfo=None) - datetime.fromisoformat(cutoff)
    assert timedelta(days=29, hours=23) < age < timedelta(days=30, hours=1)


def test_purge_failure_never_raises(tmp_path: Path):
    repo = ObservationRepository(database_path=tmp_path / "t.db")

    class Broken:
        def table(self, name):
            raise RuntimeError("down")
    repo._supabase = Broken()
    assert repo.purge_old_logs(days=5) is False
    repo._supabase = None
    assert repo.purge_old_logs() is True


def test_every_harvest_ends_with_the_purge(monkeypatch):
    from app.services import scheduler as sched

    class Quick:
        def __init__(self, repo): pass
        async def run(self, source="all"):
            raise RuntimeError("not needed")

    for name in ("AgricultureAgent", "EnvironmentAgent", "MarketsAgent", "EconomyAgent", "HealthAgent",
                 "EnergyAgent", "TransportAgent", "EducationAgent", "DemographyAgent"):
        monkeypatch.setattr(sched, name, Quick)
    service = sched.AutonomousHarvesterScheduler(interval_hours=24)
    calls = []
    monkeypatch.setattr(service.repository, "purge_old_logs", lambda: calls.append(1) or True)
    service._next_sectors = ["transport"]
    asyncio.run(service._run_harvest_job())
    assert calls == [1]
