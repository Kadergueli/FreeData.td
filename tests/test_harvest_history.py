"""Patch B — durable harvest history + manual runs from the admin area."""
import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.config import settings
from app.security import rate_limiter
from app.services import scheduler as sched_mod
from app.services.admin_store import AdminStore
from app.services.harvest_runs import HarvestRunStore, summarize_results
from app.services.scheduler import AutonomousHarvesterScheduler
from app.services.storage import SECTOR_IDS, ObservationRepository

OWNER = "owner@example.org"


# ── summarize_results ───────────────────────────────────────────────────────
def test_status_rules():
    ok = {"stored": 3, "received": 4, "rejected": 1, "errors": []}
    assert summarize_results({"a": ok, "b": ok})[0] == "completed"
    assert summarize_results({"a": ok, "b": {"error": "boom"}})[0] == "partial"
    assert summarize_results({"a": ok, "b": dict(ok, errors=["source down"])})[0] == "partial"
    assert summarize_results({"a": {"error": "x"}, "b": {"error": "y"}})[0] == "failed"
    assert summarize_results({})[0] == "completed"
    status, summary = summarize_results({"a": {"error": "x" * 999}})
    assert len(summary["a"]["error"]) == 300                       # bounded, never stores a novel


# ── store ───────────────────────────────────────────────────────────────────
def test_store_roundtrip_and_stale_runs(tmp_path):
    store = HarvestRunStore(ObservationRepository(tmp_path / "h.db"))
    rid = store.start("admin", ["health"], "me@x.org")
    assert store.list_runs()[0]["status"] == "running"
    store.finish(rid, "completed", 5, {"health": {"stored": 5}})
    row = store.list_runs()[0]
    assert (row["status"], row["total_stored"], row["sectors"], row["triggered_by"]) == ("completed", 5, ["health"], "me@x.org")
    assert row["results"] == {"health": {"stored": 5}} and row["finished_at"]

    old = store.start("scheduler", ["agriculture"], None)
    with store._sqlite() as c:
        c.execute("UPDATE harvest_runs SET started_at=? WHERE id=?", ((datetime.now(UTC) - timedelta(hours=1)).isoformat(), old))
    fresh = store.start("scheduler", ["energy"], None)
    assert store.close_stale(10) == 1                              # only the hour-old orphan
    by_id = {r["id"]: r["status"] for r in store.list_runs()}
    assert by_id[old] == "interrupted" and by_id[fresh] == "running"


def test_history_failure_never_breaks_a_harvest(tmp_path):
    store = HarvestRunStore(ObservationRepository(tmp_path / "h.db"))
    store._sqlite = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
    assert store.start("admin", [], None) is None
    store.finish(None, "completed", 0, {})                         # no id: silently nothing
    store.finish(7, "completed", 0, {})                            # db down: logged, no raise


# ── scheduler ───────────────────────────────────────────────────────────────
def _fake_agents(monkeypatch, calls, boom=()):
    def make(name):
        class A:
            def __init__(self, repo): pass
            async def run(self, source="all"):
                calls.append(name)
                if name in boom:
                    raise RuntimeError(f"{name} exploded")
                return SimpleNamespace(stored=2, model_dump=lambda mode="json": {"stored": 2, "received": 3, "rejected": 1, "errors": []})
        return A
    for cls in ("Agriculture", "Environment", "Markets", "Economy", "Health", "Energy", "Transport", "Education", "Demography"):
        monkeypatch.setattr(sched_mod, f"{cls}Agent", make(cls.lower()))


@pytest.fixture
def sched(tmp_path):
    s = AutonomousHarvesterScheduler(interval_hours=24)
    s.repository = ObservationRepository(tmp_path / "s.db")
    s.history = HarvestRunStore(s.repository)
    return s


def test_selected_sectors_only_and_run_is_recorded(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls)
    result = asyncio.run(sched.run_harvest_job(["health", "energy"], trigger="admin", triggered_by="me@x.org"))
    assert sorted(calls) == ["energy", "health"] and result["total_stored"] == 4
    row = sched.history.list_runs()[0]
    assert (row["trigger"], row["triggered_by"], row["status"], row["total_stored"]) == ("admin", "me@x.org", "completed", 4)
    assert row["sectors"] == ["health", "energy"] and row["finished_at"]
    assert sched.current_run is None and sched.get_status()["job_running"] is False


def test_all_sectors_by_default_and_partial_failure_is_visible(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls, boom=("transport",))
    asyncio.run(sched.run_harvest_job(trigger="scheduler"))
    assert len(calls) == 9
    row = sched.history.list_runs()[0]
    assert row["status"] == "partial" and row["trigger"] == "scheduler" and row["sectors"] == list(SECTOR_IDS)
    assert "transport exploded" in row["results"]["transport"]["error"]


def test_crashed_job_is_recorded_as_failed_and_unlocks(sched, monkeypatch):
    async def crash(self):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(AutonomousHarvesterScheduler, "_run_harvest_job", crash)
    with pytest.raises(RuntimeError):
        asyncio.run(sched.run_harvest_job(trigger="api"))
    assert sched.history.list_runs()[0]["status"] == "failed"
    assert sched._job_running is False and sched.current_run is None   # not stuck "running" forever


def test_unknown_sector_is_rejected_before_anything_runs(sched):
    with pytest.raises(ValueError):
        asyncio.run(sched.run_harvest_job(["nonsense"]))
    with pytest.raises(ValueError):
        sched.start_background_job(["nonsense"])
    assert sched.history.list_runs() == []


def test_public_status_does_not_leak_the_admin_email(sched, monkeypatch):
    async def slow(self):
        await asyncio.sleep(0.2)
        return {"status": "completed", "total_stored": 0, "sectors": {}}
    monkeypatch.setattr(AutonomousHarvesterScheduler, "_run_harvest_job", slow)

    async def go():
        task = asyncio.create_task(sched.run_harvest_job(["health"], "admin", "secret-admin@x.org"))
        await asyncio.sleep(0.05)
        status = sched.get_status()
        await task
        return status
    status = asyncio.run(go())
    assert status["current_run"]["sectors"] == ["health"] and "secret-admin@x.org" not in str(status)


# ── admin endpoints ─────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(tmp_path / "a.db")
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: {"tok-owner": OWNER, "tok-stranger": "x@y.org"}.get(t))
    monkeypatch.setattr(scheduler := admin_mod.scheduler_service, "history", HarvestRunStore(repo))
    monkeypatch.setattr(scheduler, "repository", repo)
    scheduler._bg_task = None
    scheduler._job_running = False
    calls = []
    _fake_agents(monkeypatch, calls)
    rate_limiter._requests.clear()
    with TestClient(main_mod.app) as c:  # one event loop for the whole test, like the real server
        c.calls, c.repo = calls, repo
        yield c


H = {"Authorization": "Bearer tok-owner"}


def test_collections_endpoints_require_an_administrator(client):
    assert client.get("/api/v1/admin/collections").status_code == 401
    assert client.post("/api/v1/admin/collections/run").status_code == 401
    bad = {"Authorization": "Bearer tok-stranger"}
    assert client.get("/api/v1/admin/collections", headers=bad).status_code == 403
    assert client.post("/api/v1/admin/collections/run", headers=bad).status_code == 403
    assert client.calls == []                                       # nothing was harvested


def test_admin_runs_chosen_sectors_and_sees_them_in_history_and_audit(client):
    r = client.post("/api/v1/admin/collections/run", json={"sectors": ["transport", "education", "transport"]}, headers=H)
    assert r.status_code == 202 and r.json() == {"status": "started"}
    for _ in range(200):  # generous: the full suite can run this on a loaded machine
        data = client.get("/api/v1/admin/collections", headers=H).json()
        if data["runs"] and data["runs"][0]["status"] != "running" and data["job_running"] is False:
            break
        time.sleep(0.1)
    run = data["runs"][0]
    assert run["status"] == "completed" and run["trigger"] == "admin" and run["triggered_by"] == OWNER
    assert run["sectors"] == ["transport", "education"] and sorted(client.calls) == ["education", "transport"]
    assert data["sector_ids"] == list(SECTOR_IDS) and data["job_running"] is False
    audit = AdminStore(client.repo).list_audit()
    assert audit[0]["action"] == "harvest_run" and audit[0]["admin_email"] == OWNER and audit[0]["target"] == "transport,education"


def test_empty_body_means_every_sector(client):
    assert client.post("/api/v1/admin/collections/run", headers=H).status_code == 202
    for _ in range(50):
        if len(client.calls) == 9:
            break
        time.sleep(0.1)
    assert sorted(client.calls) == sorted(c.lower() for c in ("Agriculture", "Environment", "Markets", "Economy", "Health", "Energy", "Transport", "Education", "Demography"))


def test_unknown_sector_is_422_and_not_audited(client):
    r = client.post("/api/v1/admin/collections/run", json={"sectors": ["health", "../etc"]}, headers=H)
    assert r.status_code == 422 and client.calls == []
    assert AdminStore(client.repo).list_audit() == []


def test_second_click_while_running_is_reported_not_stacked(client, monkeypatch):
    async def slow(self):
        await asyncio.sleep(0.5)
        return {"status": "completed", "total_stored": 0, "sectors": {}}
    monkeypatch.setattr(AutonomousHarvesterScheduler, "_run_harvest_job", slow)
    assert client.post("/api/v1/admin/collections/run", headers=H).json()["status"] == "started"
    assert client.post("/api/v1/admin/collections/run", headers=H).json()["status"] == "already_running"
    assert len([a for a in AdminStore(client.repo).list_audit() if a["action"] == "harvest_run"]) == 1
    time.sleep(0.8)


def test_unreadable_history_is_a_clear_503(client, monkeypatch):
    monkeypatch.setattr(admin_mod.scheduler_service.history, "list_runs", lambda n: (_ for _ in ()).throw(RuntimeError("db")))
    assert client.get("/api/v1/admin/collections", headers=H).status_code == 503
