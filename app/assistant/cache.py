"""Cache mémoire (5 min) devant le dépôt : les données ne changent qu'à la collecte, et chaque
appel Supabase coûte ~100-300 ms. Les erreurs ne sont jamais mises en cache."""
from __future__ import annotations

import threading
import time

TTL_SECONDS = 300.0
MAX_ENTRIES = 400

_lock = threading.Lock()
_store: dict[tuple, tuple[float, object]] = {}


def clear() -> None:
    with _lock:
        _store.clear()


class CachedRepo:
    """Enveloppe `list_observations` / `region_names` / `get_stats` d'un dépôt avec un cache partagé."""

    def __init__(self, repo, ttl: float = TTL_SECONDS) -> None:
        self._repo, self._ttl = repo, ttl

    def _cached(self, key: tuple, loader):
        full = (self._repo, *key)        # la référence garde le dépôt en vie : pas de réutilisation d'identité
        now = time.monotonic()
        with _lock:
            hit = _store.get(full)
            if hit and now - hit[0] < self._ttl:
                return hit[1]
        value = loader()                      # une exception traverse, rien n'est mémorisé
        with _lock:
            if len(_store) >= MAX_ENTRIES:
                _store.clear()
            _store[full] = (now, value)
        return value

    def list_observations(self, sector=None, region=None, limit=100, q=None):
        return self._cached(("obs", sector, region, limit, q),
                            lambda: self._repo.list_observations(sector=sector, region=region, limit=limit, q=q))

    def region_names(self):
        if hasattr(self._repo, "region_names"):
            return self._cached(("regions",), lambda: list(self._repo.region_names()))
        return self._cached(("regions",), lambda: list(((self._repo.get_stats() or {}).get("regions") or {}).keys()))
