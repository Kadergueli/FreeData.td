"""Security tests for POST /api/v1/collection/* — auth split between public
(rate-limit only) and admin-only (secret key + rate-limit) endpoints.

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


def test_public_sectors_do_not_require_a_key() -> None:
    """agriculture/environment/markets/economy are called by the public
    'COLLECT LIVE DATA' button — no secret key should be required."""
    client = TestClient(app)
    for sector in PUBLIC_SECTORS:
        response = client.post(f"/api/v1/collection/{sector}")
        assert response.status_code == 202, f"{sector} should be reachable without a key (got {response.status_code}: {response.text})"


def test_public_sectors_enforce_rate_limit() -> None:
    """After collection_rate_limit_per_hour requests to the SAME public sector
    endpoint from one IP, further requests are rejected with 429."""
    client = TestClient(app)
    limit = settings.collection_rate_limit_per_hour

    statuses = [client.post("/api/v1/collection/agriculture").status_code for _ in range(limit)]
    assert all(s == 202 for s in statuses), statuses

    response = client.post("/api/v1/collection/agriculture")
    assert response.status_code == 429


def test_public_sectors_share_one_rate_limit_bucket_per_ip() -> None:
    """The rate limit is per-IP, not per-sector: mixing calls across the 4
    public sectors from the same IP should still hit the shared limit."""
    client = TestClient(app)
    limit = settings.collection_rate_limit_per_hour

    statuses = []
    for i in range(limit):
        sector = PUBLIC_SECTORS[i % len(PUBLIC_SECTORS)]
        statuses.append(client.post(f"/api/v1/collection/{sector}").status_code)
    assert all(s == 202 for s in statuses), statuses

    response = client.post(f"/api/v1/collection/{PUBLIC_SECTORS[0]}")
    assert response.status_code == 429


def test_admin_only_sectors_reject_missing_key() -> None:
    """transport/education are never called by any UI button — they keep
    requiring a secret key. With COLLECTION_API_KEY configured (forced by the
    fixture above) but no header sent, the request must be rejected with 401."""
    client = TestClient(app)
    for sector in ADMIN_ONLY_SECTORS:
        response = client.post(f"/api/v1/collection/{sector}")
        assert response.status_code == 401, f"{sector} must reject a missing key (got {response.status_code}: {response.text})"


def test_admin_only_sectors_reject_wrong_key() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/collection/transport",
        headers={"X-Collection-Key": "definitely-wrong-key"},
    )
    assert response.status_code == 401


def test_admin_only_sectors_accept_valid_key() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/collection/transport",
        headers={"X-Collection-Key": TEST_COLLECTION_API_KEY},
    )
    assert response.status_code == 202, response.text


def test_run_scheduled_harvest_still_requires_key() -> None:
    """The scheduler's manual trigger is never called by any UI button either —
    same admin-only treatment as transport/education."""
    client = TestClient(app)
    response = client.post("/api/v1/collection/run-scheduled-harvest")
    assert response.status_code == 401


def test_public_and_admin_rate_limit_buckets_are_independent() -> None:
    """Exhausting the public rate-limit bucket must NOT lock out an
    authenticated admin call on a different (key-protected) endpoint, and
    vice versa — they use separate bucket namespaces."""
    client = TestClient(app)
    limit = settings.collection_rate_limit_per_hour

    for _ in range(limit):
        client.post("/api/v1/collection/agriculture")
    exhausted = client.post("/api/v1/collection/agriculture")
    assert exhausted.status_code == 429

    # The admin-only endpoint should be unaffected by the public bucket being full.
    admin_response = client.post(
        "/api/v1/collection/transport",
        headers={"X-Collection-Key": TEST_COLLECTION_API_KEY},
    )
    assert admin_response.status_code == 202, admin_response.text
