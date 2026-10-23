"""Patch A — admin area: only confirmed administrators get in, everything is audited."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.admin import compute_alerts
from app.config import settings
from app.schemas import ObservationCreate
from app.security import rate_limiter
from app.services.admin_store import AdminStore
from app.services.storage import ObservationRepository

OWNER = "owner@example.org"
OTHER_ADMIN = "second@example.org"
STRANGER = "stranger@example.org"
USERS = {"tok-owner": OWNER, "tok-admin": OTHER_ADMIN, "tok-stranger": STRANGER}


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(tmp_path / "admin.db")
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda token: USERS.get(token))
    AdminStore(repo).add_admin(OTHER_ADMIN, "admin", OWNER)
    rate_limiter._requests.clear()
    c = TestClient(main_mod.app)
    c.repo = repo
    return c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_no_token_is_401_and_unknown_token_is_401(client):
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.get("/api/v1/admin/overview", headers=auth("garbage")).status_code == 401


def test_signed_in_non_admin_is_403(client):
    r = client.get("/api/v1/admin/overview", headers=auth("tok-stranger"))
    assert r.status_code == 403


def test_owner_from_env_and_admin_from_table_get_in_with_their_roles(client):
    assert client.get("/api/v1/admin/me", headers=auth("tok-owner")).json() == {"email": OWNER, "role": "owner"}
    assert client.get("/api/v1/admin/me", headers=auth("tok-admin")).json() == {"email": OTHER_ADMIN, "role": "admin"}


def test_not_configured_means_503_never_open_access(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_anon_key", None)
    assert client.get("/api/v1/admin/overview", headers=auth("tok-owner")).status_code == 503
    assert client.get("/api/v1/config").json()["admin"] == {"enabled": False, "supabase_url": None, "anon_key": None}


def test_public_config_exposes_only_the_publishable_key(client):
    cfg = client.get("/api/v1/config").json()["admin"]
    assert cfg == {"enabled": True, "supabase_url": "https://example.supabase.co", "anon_key": "anon-key"}


def test_repeated_failures_are_rate_limited(client):
    codes = [client.get("/api/v1/admin/me", headers=auth("bad")).status_code for _ in range(32)]
    assert codes[0] == 401 and codes[-1] == 429


def test_login_is_audited_and_readable_by_admins_only(client):
    client.post("/api/v1/admin/session", headers=auth("tok-admin"))
    entries = client.get("/api/v1/admin/audit-log", headers=auth("tok-owner")).json()["entries"]
    assert entries[0]["admin_email"] == OTHER_ADMIN and entries[0]["action"] == "login"
    assert client.get("/api/v1/admin/audit-log").status_code == 401


def test_overview_requires_admin_and_has_the_expected_shape(client):
    client.repo.upsert_many([ObservationCreate(
        sector="health", indicator="Mortalité", value=1.0, unit="%", reference_date="2024-01-01",
        country_code="TCD", region="Lac", source="World Bank", source_url="https://x.org",
        license="CC-BY 4.0", notes="n")])
    data = client.get("/api/v1/admin/overview", headers=auth("tok-owner")).json()
    assert {"service", "data", "quality", "alerts", "health"} <= set(data)
    health = next(s for s in data["data"]["sectors"] if s["id"] == "health")
    assert health["count"] == 1 and health["last_published"]
    assert next(s for s in data["data"]["sectors"] if s["id"] == "transport")["count"] == 0


# ── token verification against Supabase Auth ───────────────────────────────────

def _fake_get(status, body):
    def get(url, headers=None, timeout=None):
        assert url.endswith("/auth/v1/user") and headers["Authorization"] == "Bearer T"
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))
    return get


def test_verify_accepts_only_confirmed_emails(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "k")
    admin_mod._TOKEN_CACHE.clear()
    monkeypatch.setattr(httpx, "get", _fake_get(200, {"email": "A@Example.org", "email_confirmed_at": "2026-01-01"}))
    assert admin_mod.verify_access_token("T") == "a@example.org"
    admin_mod._TOKEN_CACHE.clear()
    monkeypatch.setattr(httpx, "get", _fake_get(200, {"email": "a@example.org", "email_confirmed_at": None}))
    assert admin_mod.verify_access_token("T") is None
    admin_mod._TOKEN_CACHE.clear()
    monkeypatch.setattr(httpx, "get", _fake_get(401, {"msg": "bad"}))
    assert admin_mod.verify_access_token("T") is None


def test_verify_outage_is_503_not_a_silent_denial(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "k")
    admin_mod._TOKEN_CACHE.clear()

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(Exception) as exc:
        admin_mod.verify_access_token("T2")
    assert getattr(exc.value, "status_code", None) == 503


# ── alerts ─────────────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def _alerts(**over):
    base = dict(
        stats={"sectors": {s: 10 for s in admin_mod.SECTOR_IDS}, "last_update": (NOW - timedelta(hours=3)).isoformat()},
        sector_last={s: (NOW - timedelta(hours=3)).isoformat() for s in admin_mod.SECTOR_IDS},
        scheduler={"last_run": NOW.isoformat(), "last_result": {"sectors": {}}}, audit={}, llm_configured=True, now=NOW)
    base.update(over)
    return compute_alerts(**base)


def test_healthy_system_has_no_alerts():
    assert _alerts() == []


def test_stalled_collection_is_critical_and_sorted_first():
    alerts = _alerts(stats={"sectors": {"agriculture": 0, "health": 5}, "last_update": (NOW - timedelta(days=40)).isoformat()},
                     audit={"nb_anomalies": 4})
    assert alerts[0]["level"] == "critical" and alerts[0]["code"] == "collection_stalled"
    assert alerts[0]["params"]["days"] == 40
    codes = [a["code"] for a in alerts]
    assert "sector_empty" in codes and codes[-1] == "anomalies"          # info last


def test_failed_sector_and_missing_llm_are_reported():
    alerts = _alerts(scheduler={"last_run": NOW.isoformat(), "last_result": {"sectors": {"energy": {"error": "timeout"}}}},
                     llm_configured=False)
    by_code = {a["code"]: a for a in alerts}
    assert by_code["harvest_error"]["params"]["sector"] == "energy" and "timeout" in by_code["harvest_error"]["message"]
    assert by_code["llm_missing"]["level"] == "info"


def test_unreadable_database_is_critical():
    assert _alerts(stats={"sectors": {}, "last_update": None})[0]["code"] == "data_unreadable"
