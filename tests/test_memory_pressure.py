"""Guards for the Render 'exceeded memory limit' fix: cached aggregates,
bounded over-fetch, and a rate limiter that does not grow forever."""
from datetime import UTC, datetime, timedelta

from app.security import RateLimiter
from app.services import storage
from app.services.storage import ObservationRepository


class _Q:
    def __init__(self, log): self.log = log
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, n): self.log.append(n); return self
    @property
    def not_(self): return self
    def is_(self, *a, **k): return self
    def execute(self):
        class R: data = [{"id": 1, "valeur": 1.0, "unite": "u", "secteur": "agriculture", "indicateur": "i", "source_api": "s",
                          "date_reference": "2020-01-01", "region": "Lac"}]
        return R()


class _C:
    def __init__(self): self.calls = 0; self.limits = []
    def table(self, name): self.calls += 1; return _Q(self.limits)


def _repo():
    r = ObservationRepository.__new__(ObservationRepository)
    r._supabase = _C()
    return r


def test_catalog_and_regions_are_cached_until_write():
    storage.invalidate_cache()
    r = _repo()
    r.catalog(); n = r._supabase.calls
    r.catalog(); r.catalog()
    assert r._supabase.calls == n, "second/third catalog() must hit the cache"
    r.list_regions(); m = r._supabase.calls
    r.list_regions()
    assert r._supabase.calls == m
    storage.invalidate_cache()
    r.catalog()
    assert r._supabase.calls > m, "invalidate_cache() must force a refresh"


def test_failed_catalog_is_not_cached():
    storage.invalidate_cache()
    r = ObservationRepository.__new__(ObservationRepository)
    class Boom:
        def table(self, n): raise RuntimeError("socket")
    r._supabase = Boom()
    assert r.catalog() == []
    assert storage._cache_get("catalog", 60) is None


def test_overfetch_is_bounded():
    storage.invalidate_cache()
    r = _repo()
    r.list_observations(limit=5000)
    assert max(r._supabase.limits) <= 7500  # was 20000 (limit*4)


def test_rate_limiter_sweeps_idle_buckets():
    rl = RateLimiter()
    for i in range(50):
        rl.allow(f"ip{i}", 5)
    old = datetime.now(UTC) - timedelta(hours=2)
    for d in rl._requests.values():
        d.clear(); d.append(old)
    rl._last_sweep = datetime.now(UTC) - timedelta(minutes=30)
    rl.allow("fresh", 5)
    assert list(rl._requests) == ["fresh"]
