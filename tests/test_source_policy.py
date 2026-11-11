"""Admin space "Sources & licences": merged register + decisions, audited updates."""
import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.config import settings
from app.licences import load_register
from app.security import rate_limiter
from app.services.source_policy import ALTERNATIVES, default_policy, row_source_id
from app.services.storage import ObservationRepository

OWNER = "owner@example.org"


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(tmp_path / "sp.db")
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: OWNER if t == "tok" else None)
    rate_limiter._requests.clear()
    return TestClient(main_mod.app)


H = {"Authorization": "Bearer tok"}


def test_requires_admin(client):
    assert client.get("/api/v1/admin/sources").status_code == 401
    assert client.put("/api/v1/admin/sources/imf", json={"status": "paused"}).status_code == 401


def test_overview_merges_register_and_defaults(client):
    r = client.get("/api/v1/admin/sources", headers=H).json()
    by = {s["id"]: s for s in r["sources"]}
    assert len(by) == len(load_register())
    assert by["world-bank"]["policy"]["layer"] == "both"
    assert by["open-meteo"]["policy"]["layer"] == "open"
    assert by["open-meteo"]["policy"]["limit_day"] == 10000
    assert by["copernicus-era5"]["policy"]["status"] == "planned"
    assert by["copernicus-era5"]["commercial_safe"] is True
    assert r["alternatives"] == ALTERNATIVES and set(ALTERNATIVES[0]["sources"]) <= set(by)


def test_update_is_saved_audited_and_warns(client):
    r = client.put("/api/v1/admin/sources/open-meteo", headers=H,
                   json={"layer": "both", "limit_day": 8000, "notes": " garder 20 % de marge "})
    assert r.json()["status"] == "saved" and set(r.json()["changes"]) == {"layer", "limit_day", "notes"}
    by = {s["id"]: s for s in client.get("/api/v1/admin/sources", headers=H).json()["sources"]}
    pol = by["open-meteo"]["policy"]
    assert (pol["layer"], pol["limit_day"], pol["notes"], pol["customised"]) == ("both", 8000, "garder 20 % de marge", True)
    assert pol["limit_hour"] == 5000                     # untouched fields keep their value
    assert "commercial_not_cleared" in by["open-meteo"]["warnings"]
    audit = client.get("/api/v1/admin/audit-log", headers=H).json()["entries"]
    assert any(e["action"] == "source_policy" and e["target"] == "open-meteo" for e in audit)
    assert client.put("/api/v1/admin/sources/open-meteo", headers=H, json={"limit_day": 8000}).json() == {"status": "unchanged"}


def test_rejects_unknown_source_and_bad_values(client):
    assert client.put("/api/v1/admin/sources/nope", headers=H, json={"status": "paused"}).status_code == 404
    assert client.put("/api/v1/admin/sources/imf", headers=H, json={"status": "weird"}).status_code == 422
    assert client.put("/api/v1/admin/sources/imf", headers=H, json={"layer": "x"}).status_code == 422
    assert client.put("/api/v1/admin/sources/imf", headers=H, json={"limit_day": -1}).status_code == 422


def test_row_source_matching():
    assert row_source_id("World Bank Pink Sheet (monthly)") == "pink-sheet"
    assert row_source_id("World Bank WDI") == "world-bank"
    assert row_source_id("Open-Meteo Archive", "transport") == "open-meteo-transport"
    assert row_source_id("NASA POWER", "agriculture") == "nasa-power-agro"
    assert row_source_id("Something else") is None


def test_defaults_follow_the_licence():
    safe = next(e for e in load_register() if e["id"] == "world-bank")
    assert default_policy(safe)["layer"] == "both"
