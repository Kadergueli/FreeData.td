"""Patch 0027 — run-scheduled-harvest?background=true returns at once and can be polled."""
import asyncio
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import rate_limiter
from app.services.scheduler import scheduler_service

KEY = "test-key-background"


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(settings, "collection_api_key", KEY)
    rate_limiter._requests.clear()

    async def fake_job(self):
        self.last_run = datetime.now(UTC)
        await asyncio.sleep(0.4)
        self.last_result = {"status": "completed", "total_stored": 7, "sectors": {}}
        return self.last_result

    monkeypatch.setattr(type(scheduler_service), "_run_harvest_job", fake_job)
    scheduler_service.last_run = None
    scheduler_service.last_result = None


def test_background_returns_202_immediately_then_result_is_pollable():
    with TestClient(app) as client:
        t0 = time.perf_counter()
        resp = client.post("/api/v1/collection/run-scheduled-harvest?background=true", headers={"X-Collection-Key": KEY})
        assert resp.status_code == 202 and resp.json() == {"status": "started"}
        assert time.perf_counter() - t0 < 0.3                       # did not wait for the 0.4 s job

        again = client.post("/api/v1/collection/run-scheduled-harvest?background=true", headers={"X-Collection-Key": KEY})
        assert again.json() == {"status": "already_running"}        # no second concurrent harvest

        for _ in range(50):
            st = client.get("/api/v1/collection/scheduler-status").json()
            if st["last_result"] and not st["job_running"]:
                break
            time.sleep(0.1)
        assert st["last_result"]["total_stored"] == 7 and st["job_running"] is False


def test_background_requires_the_admin_key():
    with TestClient(app) as client:
        assert client.post("/api/v1/collection/run-scheduled-harvest?background=true").status_code == 401
        bad = client.post("/api/v1/collection/run-scheduled-harvest?background=true", headers={"X-Collection-Key": "nope"})
        assert bad.status_code == 401


def test_foreground_mode_still_returns_the_result():
    with TestClient(app) as client:
        resp = client.post("/api/v1/collection/run-scheduled-harvest", headers={"X-Collection-Key": KEY})
        assert resp.status_code == 200 and resp.json()["total_stored"] == 7
