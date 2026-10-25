import pytest

from app.security import rate_limiter
from app.services import storage


@pytest.fixture(autouse=True)
def _clear_storage_cache():
    """The aggregate cache is process-wide; isolate every test from it."""
    storage.invalidate_cache()
    yield
    storage.invalidate_cache()


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Rate-limit buckets are process-wide: one test's requests must not count against the next."""
    rate_limiter._requests.clear()
    yield
    rate_limiter._requests.clear()
