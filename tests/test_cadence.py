"""Patch 0042 — each sector is collected at the rhythm of its data."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.admin import compute_alerts
from app.services import scheduler as sched_mod
from app.services.cadence import SECTOR_CADENCE_DAYS, last_success, split_due
from app.services.harvest_runs import HarvestRunStore
from app.services.scheduler import AutonomousHarvesterScheduler
from app.services.storage import SECTOR_IDS, ObservationRepository
from tests.test_harvest_history import _fake_agents

NOW = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)


def _run(sectors, hours_ago, **per_sector):
    results = {s: {"stored": 3} for s in sectors}
    results.update(per_sector)
    return {"started_at": (NOW - timedelta(hours=hours_ago)).isoformat(), "results": results}


def test_every_sector_has_a_rhythm():
    assert set(SECTOR_CADENCE_DAYS) == set(SECTOR_IDS)


def test_never_collected_means_due():
    due, skipped = split_due([], list(SECTOR_IDS), NOW)
    assert due == list(SECTOR_IDS) and skipped == {}


def test_recent_collection_is_skipped_and_old_one_is_due():
    runs = [_run(SECTOR_IDS, 24 * 3)]   # everything collected 3 days ago
    due, skipped = split_due(runs, list(SECTOR_IDS), NOW)
    assert set(due) == {"environment", "agriculture"}               # daily ones
    assert set(skipped) == {"markets", "transport", "health", "education", "economy", "energy", "demography"}


def test_weekly_and_monthly_become_due_on_time():
    due, _ = split_due([_run(SECTOR_IDS, 24 * 8)], list(SECTOR_IDS), NOW)
    assert {"markets", "transport"} <= set(due) and "health" not in due
    due, _ = split_due([_run(SECTOR_IDS, 24 * 31)], list(SECTOR_IDS), NOW)
    assert set(due) == set(SECTOR_IDS)


def test_daily_run_is_not_skipped_by_a_few_minutes_of_drift():
    # yesterday's run started 23 h 56 min ago: today's 03:00 run must still collect
    due, _ = split_due([_run(["environment"], 23.9)], ["environment"], NOW)
    assert due == ["environment"]


def test_failed_sector_stays_due():
    runs = [_run(["markets", "health", "energy"], 1,
                 markets={"error": "boom"},
                 health={"stored": 0, "errors": ["source failed: who"]},
                 energy={"stored": 4, "errors": ["one source failed"]})]
    due, skipped = split_due(runs, ["markets", "health", "energy"], NOW)
    assert set(due) == {"markets", "health"}     # failed → retried
    assert "energy" in skipped                   # partial but stored data → counted


def test_last_success_takes_the_newest_good_run():
    runs = [_run(["health"], 100), _run(["health"], 5), _run(["health"], 1, health={"error": "x"})]
    assert last_success(runs, "health") == NOW - timedelta(hours=5)


# ── scheduler ──
@pytest.fixture
def sched(tmp_path):
    s = AutonomousHarvesterScheduler(interval_hours=24)
    s.repository = ObservationRepository(tmp_path / "c.db")
    s.history = HarvestRunStore(s.repository)
    return s


def test_automatic_run_collects_only_due_sectors_then_skips_them(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls)
    first = asyncio.run(sched.run_harvest_job(trigger="scheduler", only_due=True))
    assert len(calls) == len(SECTOR_IDS) and first["skipped"] == {}          # first time: everything is due
    calls.clear()
    second = asyncio.run(sched.run_harvest_job(trigger="scheduler", only_due=True))
    assert calls == []                                          # collected a minute ago: nothing is due
    assert set(second["skipped"]) == set(SECTOR_IDS)
    assert sched.last_run is not None


def test_nothing_due_still_completes_and_collects_nothing(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls)
    asyncio.run(sched.run_harvest_job(trigger="scheduler"))     # everything collected just now
    calls.clear()
    # make even the daily sectors look fresh
    monkeypatch.setattr(sched_mod, "split_due", lambda runs, c: ([], {s: "later" for s in c}))
    res = asyncio.run(sched.run_harvest_job(trigger="scheduler", only_due=True))
    assert calls == [] and res["status"] == "completed" and res["total_stored"] == 0 and res["sectors"] == {}
    assert sched.get_public_status()["last_result"]["skipped"] == sorted(SECTOR_IDS)


def test_admin_run_ignores_the_rhythm(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls)
    asyncio.run(sched.run_harvest_job(trigger="scheduler"))
    calls.clear()
    asyncio.run(sched.run_harvest_job(["health", "markets"], trigger="admin", triggered_by="a@b.c"))
    assert sorted(calls) == ["health", "markets"]


def test_unreadable_history_means_everything_is_due(sched, monkeypatch):
    calls = []
    _fake_agents(monkeypatch, calls)
    monkeypatch.setattr(sched.history, "list_runs", lambda limit=30: (_ for _ in ()).throw(RuntimeError("db down")))
    asyncio.run(sched.run_harvest_job(trigger="scheduler", only_due=True))
    assert len(calls) == len(SECTOR_IDS)


def test_endpoint_collects_due_only_unless_forced(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app, scheduler_service
    seen = []

    async def fake(sectors=None, trigger="api", triggered_by=None, only_due=False):
        seen.append(only_due)
        return {"status": "completed"}
    monkeypatch.setattr(settings, "collection_api_key", "k")
    monkeypatch.setattr(scheduler_service, "run_harvest_job", fake)
    c = TestClient(app)
    h = {"X-Collection-Key": "k"}
    c.post("/api/v1/collection/run-scheduled-harvest", headers=h)
    c.post("/api/v1/collection/run-scheduled-harvest?force=true", headers=h)
    assert seen == [True, False]


# ── alerts ──
def _alerts(sector_age_days, sector):
    return compute_alerts(
        stats={"sectors": {s: 5 for s in SECTOR_IDS}, "last_update": NOW.isoformat()},
        sector_last={sector: (NOW - timedelta(days=sector_age_days)).isoformat()},
        scheduler={"last_run": NOW.isoformat(), "last_result": {"sectors": {}}}, audit={}, llm_configured=True, now=NOW)


def test_monthly_sector_does_not_alarm_after_a_normal_gap():
    assert not [a for a in _alerts(40, "health") if a["code"] == "sector_not_collected"]
    assert [a for a in _alerts(70, "health") if a["code"] == "sector_not_collected"]
    assert [a for a in _alerts(15, "environment") if a["code"] == "sector_not_collected"]
