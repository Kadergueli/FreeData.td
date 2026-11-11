import re

from fastapi.testclient import TestClient

from app.agents.base import source_terms
from app.licences import COMMERCIAL_VALUES, commercial_safe, load_register
from app.main import app
from app.services.sources import SOURCE_LABELS

client = TestClient(app)


def test_every_collectable_source_has_a_register_entry():
    ids = {e["id"] for e in load_register()}
    assert set(SOURCE_LABELS) <= ids, set(SOURCE_LABELS) - ids


def test_entries_are_well_formed():
    seen = set()
    for e in load_register():
        assert e["id"] not in seen
        seen.add(e["id"])
        assert e["commercial_use"] in COMMERCIAL_VALUES
        assert e["verified_on"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["verified_on"])
        assert e["licence"] and e["terms_url"].startswith("https://") and e["evidence"]


def test_commercial_safe_needs_both_permission_and_a_verification():
    assert commercial_safe({"commercial_use": "yes", "verified_on": "2026-11-10"})
    assert not commercial_safe({"commercial_use": "yes", "verified_on": None})
    assert not commercial_safe({"commercial_use": "conditional", "verified_on": "2026-11-10"})
    by_id = {e["id"]: e for e in load_register()}
    assert not commercial_safe(by_id["who-gho"]) and not commercial_safe(by_id["open-meteo"])
    assert commercial_safe(by_id["world-bank"])


def test_corrected_licences_are_what_new_rows_carry():
    assert source_terms("UNICEF Data", "X")[0] == "CC BY 3.0 IGO"
    assert source_terms("UNESCO UIS", "X")[0] == "CC BY-SA 4.0"
    by_id = {e["id"]: e for e in load_register()}
    assert by_id["unesco-uis"]["share_alike"] is True and by_id["unesco-uis"]["licence"] == "CC BY-SA 4.0"
    assert by_id["unicef"]["licence"] == "CC BY 3.0 IGO"


def test_api_lists_sources_with_a_summary():
    body = client.get("/api/v1/licences").json()
    assert body["summary"]["total"] == len(body["sources"]) == len(load_register())
    assert body["summary"]["unverified"] > 0 and body["summary"]["not_commercial"] >= 1
    assert all("commercial_safe" in s for s in body["sources"])
