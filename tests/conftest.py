import pytest

from app.services import storage


@pytest.fixture(autouse=True)
def _clear_storage_cache():
    """The aggregate cache is process-wide; isolate every test from it."""
    storage.invalidate_cache()
    yield
    storage.invalidate_cache()
