"""Admin: collect one sector from chosen sources, and keep each source's own result."""
import asyncio
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.config import settings
from app.schemas import CollectionResult
from app.security import rate_limiter
from app.services import scheduler as sched_mod
from app.services.admin_store import AdminStore
from app.services.cadence import last_success
from app.services.harvest_runs import HarvestRunStore, latest_by_sector, summarize_results
from app.services.scheduler import AutonomousHarvesterScheduler, agent_classes
from app.services.sources import SECTOR_SOURCES, source_catalogue, validate_sources
from app.services.storage import SECTOR_IDS, ObservationRepository


def test_every_sector_lists_exactly_the_sources_its_agent_accepts(tmp_path):
    """A source added to an agent and forgotten in the admin table (or the reverse) fails here."""
    assert set(SECTOR_SOURCES) == set(SECTOR_IDS) == set(agent_classes())
    repo = ObservationRepository(tmp_path / "s.db")
    for sector, cls in agent_classes().items():
        with pytest.raises(ValueError) as exc:
            asyncio.run(cls(repo).collect("not-a-source"))
        listed = re.search(r"Supported: (.*)\.", str(exc.value)).group(1)
        accepted = tuple(x.strip("' ") for x in listed.split(",") if x.strip("' ") not in ("all", "demo"))
        assert accepted == SECTOR_SOURCES[sector], sector


def test_catalogue_gives_a_label_to_every_source():
    cat = source_catalogue()
    assert [s["id"] for s in cat["health"]] == ["world-bank", "who-gho", "dhs", "unicef", "open-street-map"]
    assert all(s["label"] for sources in cat.values() for s in sources)


@pytest.mark.parametrize("bad,msg", [({"nope": ["world-bank"]}, "unknown sector"), ({"health": ["pink-sheet"]}, "unknown source"),
                                     ({"health": []}, "no source given")])
def test_validate_sources_names_the_problem(bad, msg):
    with pytest.raises(ValueError, match=msg):
        validate_sources(bad)
    validate_sources({"health": ["dhs"]})
    validate_sources(None)


class FakeAgent:
    outcomes: dict[str, object] = {}

    def __init__(self, repository):
        pass

    async def run(self, source="all"):
        out = self.outcomes[source]
        if isinstance(out, Exception):
            raise out
        return CollectionResult(agent="Fake", source=source, received=out["stored"], accepted=out["stored"], rejected=0,
                                stored=out["stored"], held=0, started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
                                errors=out.get("errors", []))


def _scheduler(tmp_path):
    s = AutonomousHarvesterScheduler(interval_hours=24)
    s.repository = ObservationRepository(tmp_path / "r.db")
    s.history = HarvestRunStore(s.repository)
    return s


def test_each_picked_source_keeps_its_own_result(tmp_path):
    FakeAgent.outcomes = {"who-gho": {"stored": 20, "errors": ["WHO GHO: 3/25 series empty"]}, "dhs": RuntimeError("DHS Program returned nothing")}
    res = asyncio.run(_scheduler(tmp_path)._run_sources("health", FakeAgent, ["who-gho", "dhs"]))
    assert res["stored"] == 20 and res["source"] == "who-gho,dhs"
    assert res["sources"]["who-gho"]["stored"] == 20 and res["sources"]["who-gho"]["errors"]
    assert res["sources"]["dhs"] == {"error": "DHS Program returned nothing"}
    assert "error" not in res                                  # one source worked: the sector did not fail
    assert any(e.startswith("dhs: ") for e in res["errors"])


def test_a_sector_whose_only_source_fails_is_failed(tmp_path):
    FakeAgent.outcomes = {"dhs": RuntimeError("boom")}
    res = asyncio.run(_scheduler(tmp_path)._run_sources("health", FakeAgent, ["dhs"]))
    assert res["error"] == "dhs: boom"


def test_a_source_that_never_finishes_is_stopped(tmp_path, monkeypatch):
    class Slow(FakeAgent):
        async def run(self, source="all"):
            await asyncio.sleep(5)
    monkeypatch.setattr(sched_mod, "SECTOR_TIMEOUT_SECONDS", 0.05)
    res = asyncio.run(_scheduler(tmp_path)._run_sources("health", Slow, ["dhs"]))
    assert "stopped after" in res["sources"]["dhs"]["error"]


def test_full_harvest_job_runs_only_the_chosen_source(tmp_path, monkeypatch):
    FakeAgent.outcomes = {"who-gho": {"stored": 4}}
    monkeypatch.setattr(sched_mod, "agent_classes", lambda: {"health": FakeAgent, "energy": FakeAgent})
    s = _scheduler(tmp_path)
    out = asyncio.run(s.run_harvest_job(trigger="admin", sources={"health": ["who-gho"]}))
    assert list(out["sectors"]) == ["health"] and out["total_stored"] == 4
    assert out["sectors"]["health"]["sources"]["who-gho"]["stored"] == 4


def test_run_summary_and_latest_view_keep_per_source_lines():
    results = {"health": {"agent": "H", "stored": 20, "errors": ["dhs: x"], "held": 0,
                          "sources": {"who-gho": {"stored": 20}, "dhs": {"error": "DHS Program returned nothing"}}}}
    status, summary = summarize_results(results)
    assert status == "partial" and summary["health"]["sources"]["dhs"]["error"].startswith("DHS")
    runs = [
        {"id": 2, "status": "partial", "started_at": "2026-11-08T10:00:00", "results": summary},
        {"id": 1, "status": "completed", "started_at": "2026-11-01T10:00:00",
         "results": {"health": {"stored": 99, "sources": {"dhs": {"stored": 12}, "open-street-map": {"stored": 7}}}}},
        {"id": 0, "status": "running", "started_at": "2026-11-09T10:00:00", "results": {"health": {"stored": 1}}},
    ]
    latest = latest_by_sector(runs)["health"]
    assert latest["status"] == "partial" and latest["started_at"] == "2026-11-08T10:00:00"      # the running run is ignored
    assert latest["sources"]["dhs"]["status"] == "failed"                                      # its last run, not the older success
    assert latest["sources"]["open-street-map"]["status"] == "ok" and latest["sources"]["open-street-map"]["stored"] == 7


def test_a_run_of_some_sources_does_not_make_the_sector_up_to_date():
    now = datetime.now(UTC)
    runs = [{"status": "completed", "started_at": (now - timedelta(days=1)).isoformat(),
             "results": {"health": {"stored": 20, "sources": {"who-gho": {"stored": 20}}}}}]
    assert last_success(runs, "health") is None
    runs[0]["results"]["health"].pop("sources")
    assert last_success(runs, "health") is not None


# ── admin routes ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(tmp_path / "admin.db")
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", "owner@example.org")
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda token: "owner@example.org" if token == "t" else None)
    AdminStore(repo)
    rate_limiter._requests.clear()
    return TestClient(main_mod.app)


H = {"Authorization": "Bearer t"}


def test_collections_screen_data_carries_catalogue_cadence_and_latest(client, monkeypatch):
    monkeypatch.setattr(admin_mod.scheduler_service.history, "list_runs", lambda limit: [
        {"id": 1, "status": "completed", "started_at": "2026-11-08T10:00:00", "results": {"trade": {"stored": 5}}}])
    body = client.get("/api/v1/admin/collections", headers=H).json()
    assert body["catalogue"]["trade"][1]["id"] == "pink-sheet"
    assert body["cadence_days"]["telecom"] == 30 and body["latest"]["trade"]["stored"] == 5


def test_run_one_source_from_the_admin_area(client, monkeypatch):
    calls = []
    monkeypatch.setattr(admin_mod.scheduler_service, "start_background_job",
                        lambda sectors, **kw: calls.append((sectors, kw)) or True)
    r = client.post("/api/v1/admin/collections/run", headers=H, json={"sources": {"health": ["who-gho", "dhs"]}})
    assert r.status_code == 202 and r.json() == {"status": "started"}
    assert calls[0][0] == ["health"] and calls[0][1]["sources"] == {"health": ["who-gho", "dhs"]}
    r = client.post("/api/v1/admin/collections/run", headers=H, json={"sectors": ["energy"]})
    assert calls[1][0] == ["energy"] and calls[1][1]["sources"] is None


def test_an_unknown_source_is_refused_with_422(client):
    r = client.post("/api/v1/admin/collections/run", headers=H, json={"sources": {"health": ["pink-sheet"]}})
    assert r.status_code == 422 and "unknown source" in r.json()["detail"]
    assert client.post("/api/v1/admin/collections/run", json={"sources": {"health": ["dhs"]}}).status_code == 401
