"""Patch 0038 — CSP, self-hosted scripts, trimmed public status, global AI cap, empty-source error."""
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.base import BaseAgent
from app.main import app
from app.security import RateLimiter, require_analysis_rate_limit
from app.services.scheduler import AutonomousHarvesterScheduler

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_csp_header_is_sent_and_locks_scripts_to_self():
    csp = TestClient(app).get("/").headers["content-security-policy"]
    assert "script-src 'self'" in csp and "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp


def test_no_third_party_script_or_inline_script_in_the_page():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for tag in re.findall(r"<script\b[^>]*>", html):
        src = re.search(r'src="([^"]+)"', tag)
        assert src and not src.group(1).startswith("http"), tag     # external or inline script
    charts = (STATIC / "js" / "charts.js").read_text(encoding="utf-8")
    assert "cdn.jsdelivr" not in charts and "unpkg.com" not in charts


def test_vendored_libraries_exist_and_are_served():
    client = TestClient(app)
    for name in ("lucide-0.469.0.min.js", "chart-4.4.7.umd.js"):
        assert (STATIC / "vendor" / name).stat().st_size > 100_000
        assert client.get(f"/static/vendor/{name}").status_code == 200


def test_unused_workflows_are_gone_and_ci_exists():
    workflows = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    names = {p.name for p in workflows.glob("*.yml")}
    assert "ci.yml" in names and "scheduled_harvest.yml" in names
    assert "python-publish.yml" not in names and "collect-agriculture.yml" not in names


def test_public_scheduler_status_hides_error_text(monkeypatch):
    from app import main
    sched = AutonomousHarvesterScheduler(interval_hours=24)
    sched.last_result = {"timestamp": "2026-10-24T03:00:00+00:00", "total_stored": 7, "status": "completed",
                         "sectors": {"health": {"stored": 7, "errors": ["secret url https://x?key=abc"]},
                                     "energy": {"error": "HTTPSConnectionPool(host='internal', port=443)"}}}
    monkeypatch.setattr(main, "scheduler_service", sched)
    body = TestClient(app).get("/api/v1/collection/scheduler-status").json()
    text = str(body)
    assert "secret" not in text and "HTTPSConnectionPool" not in text and "key=abc" not in text
    assert body["last_result"]["sectors"] == {"health": {"stored": 7}, "energy": {"error": True}}
    assert body["last_result"]["total_stored"] == 7
    assert "health" in str(TestClient(app).get("/api/v1/health").json()["scheduler"]["last_result"])
    assert "secret" not in str(TestClient(app).get("/api/v1/health").json())
    # the admin view keeps the details
    assert "HTTPSConnectionPool" in str(sched.get_status())


def test_global_analysis_cap_limits_all_visitors_together(monkeypatch):
    from app import security
    monkeypatch.setattr(security, "rate_limiter", RateLimiter())
    monkeypatch.setattr(security.settings, "analysis_rate_limit_per_hour", 100)
    monkeypatch.setattr(security.settings, "analysis_global_limit_per_hour", 3)

    class Req:
        def __init__(self, ip): self.client = type("C", (), {"host": ip})()

    for i in range(3):
        require_analysis_rate_limit(Req(f"10.0.0.{i}"))        # three different visitors: fine
    with pytest.raises(HTTPException) as exc:
        require_analysis_rate_limit(Req("10.0.0.99"))          # a fourth one hits the shared ceiling
    assert exc.value.status_code == 429


class _Empty(BaseAgent):
    sector = "agriculture"
    name = "empty"

    async def collect(self, source):
        return []

    def normalize(self, record):
        return None


class _Repo:
    def store_raw_batch(self, *a, **k): return None
    def upsert_many(self, *a, **k): return 0
    def store_validation_report(self, **k): pass


def test_a_source_returning_nothing_is_reported_as_an_error(tmp_path, monkeypatch, caplog):
    import asyncio
    monkeypatch.setattr(BaseAgent, "_archive_raw", lambda *a, **k: None)
    result = asyncio.run(_Empty(_Repo()).run("x"))
    assert result.received == 0 and any("no data received" in e for e in result.errors)
    assert "returned no records" in caplog.text
