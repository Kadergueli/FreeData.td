"""Tests for the region-filtering coherence fix: the Export & API page's
region filter used to be purely decorative (never sent to the backend, and
didn't even match real stored region strings like "Moundou (Logone
Occidental)"). This exercises the real, wired-up feature end-to-end."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.security import rate_limiter
from app.services.storage import ObservationRepository


def _reset():
    rate_limiter._requests.clear()


def test_list_regions_excludes_national_placeholder(tmp_path: Path):
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    obs = [
        {"sector": "agriculture", "indicator": "Test Indicator", "value": 1.0, "unit": "u",
         "reference_date": "2024-01-01", "source": "Test", "region": "national"},
        {"sector": "agriculture", "indicator": "Test Indicator", "value": 2.0, "unit": "u",
         "reference_date": "2024-01-02", "source": "Test", "region": "Moundou (Logone Occidental)"},
    ]
    from app.schemas import ObservationCreate
    repository.upsert_many([ObservationCreate(**o) for o in obs])

    regions = repository.list_regions()
    assert "national" not in [r.lower() for r in regions]
    assert "Moundou (Logone Occidental)" in regions


def test_list_observations_region_filter_matches_partial_province_name(tmp_path: Path):
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    from app.schemas import ObservationCreate
    repository.upsert_many([
        ObservationCreate(sector="agriculture", indicator="Test Indicator", value=1.0, unit="u",
                           reference_date="2024-01-01", source="Test",
                           region="Moundou (Logone Occidental)"),
        ObservationCreate(sector="agriculture", indicator="Test Indicator 2", value=2.0, unit="u",
                           reference_date="2024-01-02", source="Test",
                           region="N'Djamena (N'Djamena)"),
    ])

    results = repository.list_observations(region="Logone")
    assert len(results) == 1
    assert "Logone" in results[0]["region"]


def test_regions_endpoint_returns_real_data():
    _reset()
    client = TestClient(app)
    client.post("/api/v1/collection/agriculture?source=demo")

    r = client.get("/api/v1/regions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_export_csv_with_region_filter_has_region_in_filename():
    _reset()
    client = TestClient(app)
    r = client.get("/api/v1/export/csv?region=Logone")
    assert r.status_code == 200
    assert "Logone" in r.headers.get("content-disposition", "")


def test_export_region_filter_actually_filters_data():
    """The core coherence bug: selecting a region must change what's
    exported, not just change a display label."""
    _reset()
    client = TestClient(app)
    client.post("/api/v1/collection/agriculture?source=demo")

    all_rows = client.get("/api/v1/export/json").json()
    filtered_rows = client.get("/api/v1/export/json?region=NonExistentRegionXYZ").json()

    assert len(filtered_rows) == 0
    assert len(all_rows) >= len(filtered_rows)
