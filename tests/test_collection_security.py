"""Security tests for POST /api/v1/collection/* — every route needs the secret key
(visitors never collect; only the scheduled workflow and administrators do).

Every agent's `.collect()` is monkeypatched to avoid real network calls to
external data sources (FAOSTAT, NASA, World Bank, ...) — these tests only
exercise the authentication/rate-limit layer in app/security.py, not the
harvest logic itself, so hitting the real internet would be both slow and
unnecessary (some agents don't even support a no-network 'demo' source).
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import (
    AgricultureAgent,
    EconomyAgent,
    EducationAgent,
    EnergyAgent,
    EnvironmentAgent,
    HealthAgent,
    MarketsAgent,
    TransportAgent,
    app,
)
from app.security import rate_limiter

PUBLIC_SECTORS = ["agriculture", "environment", "markets", "economy", "health", "energy"]
ADMIN_ONLY_SECTORS = ["transport", "education"]
ALL_AGENT_CLASSES = [
    AgricultureAgent, EnvironmentAgent, MarketsAgent,
    EconomyAgent, TransportAgent, EducationAgent,
    HealthAgent, EnergyAgent,
]


TEST_COLLECTION_API_KEY = "test-collection-key-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _no_network_and_clean_rate_limiter(monkeypatch):
    """Applied to every test in this file automatically."""

    async def fake_collect(self, source: str) -> list[dict]:
        return []

    for agent_cls in ALL_AGENT_CLASSES:
        monkeypatch.setattr(agent_cls, "collect", fake_collect)

    # Force a deterministic key so the "valid key" / "wrong key" tests below
    # actually exercise both branches, regardless of whether this environment
    # happens to have COLLECTION_API_KEY set in its .env.
    monkeypatch.setattr(settings, "collection_api_key", TEST_COLLECTION_API_KEY)

    rate_limiter._requests.clear()
    yield
    rate_limiter._requests.clear()


ALL_SECTORS = PUBLIC_SECTORS + ADMIN_ONLY_SECTORS


def test_every_collection_route_rejects_a_missing_key() -> None:
    """No visitor can trigger a collection: every sector route needs the key."""
    client = TestClient(app)
    for sector in ALL_SECTORS:
        response = client.post(f"/api/v1/collection/{sector}")
        assert response.status_code == 401, f"{sector}: {response.status_code} {response.text}"


def test_every_collection_route_rejects_a_wrong_key() -> None:
    client = TestClient(app)
    for sector in ALL_SECTORS:
        response = client.post(f"/api/v1/collection/{sector}", headers={"X-Collection-Key": "wrong"})
        assert response.status_code == 401, sector


def test_every_collection_route_accepts_the_valid_key() -> None:
    client = TestClient(app)
    for sector in ALL_SECTORS:
        response = client.post(f"/api/v1/collection/{sector}", headers={"X-Collection-Key": TEST_COLLECTION_API_KEY})
        assert response.status_code == 202, f"{sector}: {response.text}"


def test_collection_is_disabled_when_no_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "collection_api_key", "")
    client = TestClient(app)
    for sector in ALL_SECTORS:
        assert client.post(f"/api/v1/collection/{sector}").status_code == 503, sector


def test_run_scheduled_harvest_requires_key() -> None:
    assert TestClient(app).post("/api/v1/collection/run-scheduled-harvest").status_code == 401


def test_collection_rate_limit_applies_even_with_the_key() -> None:
    client = TestClient(app)
    headers = {"X-Collection-Key": TEST_COLLECTION_API_KEY}
    limit = settings.collection_rate_limit_per_hour
    assert all(client.post("/api/v1/collection/agriculture", headers=headers).status_code == 202 for _ in range(limit))
    assert client.post("/api/v1/collection/agriculture", headers=headers).status_code == 429
