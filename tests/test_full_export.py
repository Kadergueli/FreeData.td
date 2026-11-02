"""GET /api/v1/export/{csv,json}?full=true streams every row; /observations pages with offset."""
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.schemas import ObservationCreate
from app.security import rate_limiter
from app.services.storage import ObservationRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo.upsert_many([ObservationCreate(sector="markets", indicator=f"I{i}", value=float(i), unit="u",
                                        reference_date="2024-01-01", source="Test", region="Lac") for i in range(2600)])
    monkeypatch.setattr(main, "repository", repo)
    rate_limiter._requests.clear()
    return TestClient(main.app)


def test_normal_export_is_still_capped_by_the_server_limit(client, monkeypatch):
    monkeypatch.setattr(main, "EXPORT_LIMIT", 1000)
    r = client.get("/api/v1/export/csv?sector=markets")
    assert r.headers["X-Export-Truncated"] == "true"
    assert len(list(csv.DictReader(io.StringIO(r.text)))) == 1000


def test_full_csv_has_every_row(client, monkeypatch):
    monkeypatch.setattr(main, "EXPORT_LIMIT", 1000)
    r = client.get("/api/v1/export/csv?sector=markets&full=true")
    assert r.status_code == 200 and "X-Export-Truncated" not in r.headers
    assert "full.csv" in r.headers["Content-Disposition"]
    assert len(list(csv.DictReader(io.StringIO(r.text)))) == 2600


def test_full_json_is_one_valid_array(client):
    r = client.get("/api/v1/export/json?sector=markets&full=true")
    data = json.loads(r.text)
    assert len(data) == 2600 and data[0]["sector"] == "markets"


def test_full_export_of_nothing_is_announced(client):
    r = client.get("/api/v1/export/csv?sector=energy&full=true")
    assert r.headers["X-Export-Rows"] == "0"


def test_full_export_slots_are_released(client):
    for _ in range(4):
        assert client.get("/api/v1/export/csv?sector=markets&full=true").status_code == 200


def test_too_many_full_exports_at_once_get_429(client):
    held = [main._FULL_EXPORT_SLOTS.acquire(blocking=False) for _ in range(2)]
    try:
        r = client.get("/api/v1/export/csv?sector=markets&full=true")
        assert r.status_code == 429 and r.headers["Retry-After"]
    finally:
        for h in held:
            if h:
                main._FULL_EXPORT_SLOTS.release()


def test_observations_pages_with_offset(client):
    got, offset = 0, 0
    while True:
        r = client.get(f"/api/v1/observations?sector=markets&limit=1000&offset={offset}")
        got += len(r.json())
        nxt = r.headers.get("X-Next-Offset")
        if nxt is None:
            break
        offset = int(nxt)
    assert got == 2600
