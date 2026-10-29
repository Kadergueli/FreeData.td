"""Patch 0059 — security audit fixes."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import MAX_FAILED_COLLECTION_KEYS, rate_limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    rate_limiter._requests.clear()
    yield
    rate_limiter._requests.clear()


def test_wrong_collection_keys_are_limited_and_right_key_no_longer_accepted_once_blocked(monkeypatch):
    monkeypatch.setattr(settings, "collection_api_key", "s3cret-key")
    codes = [client.post("/api/v1/collection/energy", headers={"X-Collection-Key": f"guess{i}"}).status_code
             for i in range(MAX_FAILED_COLLECTION_KEYS + 3)]
    assert codes[:MAX_FAILED_COLLECTION_KEYS] == [401] * MAX_FAILED_COLLECTION_KEYS
    assert codes[MAX_FAILED_COLLECTION_KEYS:] == [429] * 3
    # blocked: even the right key gets the same answer, so a guess cannot be confirmed
    r = client.post("/api/v1/collection/energy", headers={"X-Collection-Key": "s3cret-key"})
    assert r.status_code == 429


def test_few_wrong_keys_do_not_block_the_right_one(monkeypatch):
    monkeypatch.setattr(settings, "collection_api_key", "s3cret-key")
    for i in range(3):
        assert client.post("/api/v1/collection/energy", headers={"X-Collection-Key": "bad"}).status_code == 401
    r = client.post("/api/v1/collection/nope", headers={"X-Collection-Key": "s3cret-key"})
    assert r.status_code != 401 and r.status_code != 429


def test_non_ascii_key_does_not_crash(monkeypatch):
    monkeypatch.setattr(settings, "collection_api_key", "s3cret-key")
    r = client.post("/api/v1/collection/energy", headers={"X-Collection-Key": "clé-é".encode("latin-1")})
    assert r.status_code == 401


def test_rate_limited_response_carries_security_headers(monkeypatch):
    monkeypatch.setattr(settings, "read_rate_limit_per_minute", 1)
    client.get("/api/v1/stats")
    r = client.get("/api/v1/stats")
    assert r.status_code == 429
    for h in ("Content-Security-Policy", "X-Content-Type-Options", "Strict-Transport-Security"):
        assert h in r.headers


def test_public_error_details_do_not_leak_internals(monkeypatch):
    import app.main as m
    monkeypatch.setattr(m, "observations_to_parquet",
                        lambda rows: (_ for _ in ()).throw(RuntimeError("secret /srv/path/leak")))
    r = client.get("/api/v1/export/parquet")
    assert r.status_code == 503 and "leak" not in r.text


def test_cross_sector_samples_every_sector(monkeypatch):
    import app.main as m
    from app.services.storage import invalidate_cache
    invalidate_cache()
    seen = []

    def spy(sector=None, **kw):
        seen.append(sector)
        return []
    monkeypatch.setattr(m.repository, "list_observations", spy)
    client.get("/api/v1/insights/cross-sector")
    assert sorted(seen) == sorted(m.SECTOR_IDS)
