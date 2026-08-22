from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_study_endpoint_accessible_without_key() -> None:
    client = TestClient(app)
    # Without observations, endpoint returns 422 (unprocessable entity)
    response = client.post("/api/v1/studies")
    assert response.status_code in (200, 422, 503)

