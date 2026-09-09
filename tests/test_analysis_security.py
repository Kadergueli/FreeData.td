from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import rate_limiter


def test_study_endpoint_accessible_without_key() -> None:
    """No secret key is required — this is a public button, protected by
    per-IP rate limiting only (see app/security.py for the rationale)."""
    rate_limiter._requests.clear()
    client = TestClient(app)
    response = client.post("/api/v1/studies")
    # Without observations, endpoint returns 422/503; with observations but no
    # Groq key configured, the agent still returns 200 with a statistical fallback.
    assert response.status_code in (200, 422, 503)


def test_study_endpoint_enforces_rate_limit() -> None:
    """After analysis_rate_limit_per_hour requests from the same IP, further
    requests are rejected with 429 — this is the actual abuse protection now
    that there's no secret key gating the endpoint."""
    rate_limiter._requests.clear()
    client = TestClient(app)
    limit = settings.analysis_rate_limit_per_hour

    statuses = [client.post("/api/v1/studies").status_code for _ in range(limit)]
    assert all(s in (200, 422, 503) for s in statuses)

    # One more request beyond the limit must be rate-limited.
    response = client.post("/api/v1/studies")
    assert response.status_code == 429
