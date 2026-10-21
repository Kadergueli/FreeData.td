"""Patch 0024 — /health exposes real limits and export capabilities; SQLite audit has no fake score."""
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_limits_and_parquet_capability():
    body = TestClient(app).get("/api/v1/health").json()
    assert set(body["limits"]) == {"collection_per_hour", "analysis_per_hour"}
    assert all(isinstance(v, int) and v > 0 for v in body["limits"].values())
    assert isinstance(body["exports"]["parquet"], bool)
