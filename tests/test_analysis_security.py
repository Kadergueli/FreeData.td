from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_study_endpoint_rejects_request_without_key() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/studies")
    # 503 if ANALYSIS_API_KEY isn't configured on the server, 401 otherwise.
    assert response.status_code in (401, 503)


def test_study_endpoint_rejects_wrong_key() -> None:
    if not settings.analysis_api_key:
        return  # Nothing to test against a server with no key configured.
    client = TestClient(app)
    response = client.post("/api/v1/studies", headers={"X-Analysis-Key": "wrong-key"})
    assert response.status_code == 401


def test_study_endpoint_accessible_with_valid_key() -> None:
    if not settings.analysis_api_key:
        return  # Nothing to test against a server with no key configured.
    client = TestClient(app)
    response = client.post(
        "/api/v1/studies",
        headers={"X-Analysis-Key": settings.analysis_api_key},
    )
    # Without observations, endpoint returns 422 (unprocessable entity)
    assert response.status_code in (200, 422)

