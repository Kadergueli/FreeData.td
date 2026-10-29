from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from threading import Lock

from fastapi import Header, HTTPException, Request

from app.config import settings


class RateLimiter:
    """Generic in-memory rate limiter, keyed by an arbitrary bucket id (e.g. 'analysis:<ip>')."""

    def __init__(self) -> None:
        self._requests: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()
        self._last_sweep = datetime.now(UTC)

    def _sweep(self, now: datetime, threshold: datetime) -> None:
        """Drop buckets with no request in the last hour. Without this the dict
        gains one entry per distinct client forever (slow memory growth)."""
        for key in [k for k, d in self._requests.items() if not d or d[-1] < threshold]:
            del self._requests[key]
        self._last_sweep = now

    def blocked(self, client_id: str, limit: int, window: timedelta = timedelta(hours=1)) -> bool:
        """True if the client already used up `limit` requests in the window. Does not count."""
        threshold = datetime.now(UTC) - window
        with self._lock:
            timestamps = self._requests.get(client_id)
            if not timestamps:
                return False
            return sum(1 for t in timestamps if t >= threshold) >= limit

    def allow(self, client_id: str, limit: int, window: timedelta = timedelta(hours=1)) -> bool:
        """True if the client made fewer than `limit` requests in the last `window` (max 1 hour)."""
        now = datetime.now(UTC)
        threshold = now - window
        with self._lock:
            if (now - self._last_sweep) > timedelta(minutes=10):
                self._sweep(now, now - timedelta(hours=1))
            timestamps = self._requests[client_id]
            while timestamps and timestamps[0] < threshold:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            return True


rate_limiter = RateLimiter()
# Kept for backward compatibility with any existing imports.
analysis_rate_limiter = rate_limiter


def require_analysis_rate_limit(request: Request) -> None:
    """Rate-limit study generation per IP — no secret key.

    This endpoint is called by a public, unauthenticated frontend button, so a
    shared secret can't protect it without being exposed to every visitor (which
    would defeat the point). Rate limiting alone is the honest trade-off: it
    won't stop a determined abuser rotating IPs, but it caps the cost of casual
    repeated clicks, which is the actual risk for a public "Generate Report" button.
    """
    client_id = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(f"analysis:{client_id}", settings.analysis_rate_limit_per_hour):
        raise HTTPException(status_code=429, detail="Study-generation rate limit reached. Try again later.")
    # Global ceiling, checked after the per-IP one so a blocked visitor does not use up the shared budget.
    if not rate_limiter.allow("analysis:*global*", settings.analysis_global_limit_per_hour):
        raise HTTPException(status_code=429, detail="Study generation is busy right now. Try again later.")


def require_collection_access(request: Request, x_collection_key: str | None = Header(default=None)) -> None:
    """Require a server-side secret and limit manual/triggered data-collection runs.

    Every collection endpoint uses it: visitors never trigger a collection (the public UI
    has no such button). Only the scheduled workflow (which holds the key) and scripts of
    the administrators call these routes; the admin area has its own authenticated routes.
    """
    if not settings.collection_api_key:
        raise HTTPException(status_code=503, detail="COLLECTION_API_KEY is not configured on the server.")
    client_id = request.client.host if request.client else "unknown"
    # Wrong keys are counted per client and the door closes BEFORE the key is compared,
    # so a blocked client cannot tell a right guess from a wrong one (no brute force).
    fail_bucket = f"collection-fail:{client_id}"
    if rate_limiter.blocked(fail_bucket, MAX_FAILED_COLLECTION_KEYS):
        raise HTTPException(status_code=429, detail="Too many invalid keys. Try again later.")
    if not x_collection_key or not compare_digest(x_collection_key.encode(), settings.collection_api_key.encode()):
        rate_limiter.allow(fail_bucket, MAX_FAILED_COLLECTION_KEYS)
        raise HTTPException(status_code=401, detail="A valid X-Collection-Key is required.")
    if not rate_limiter.allow(f"collection-admin:{client_id}", settings.collection_rate_limit_per_hour):
        raise HTTPException(status_code=429, detail="Collection rate limit reached. Try again later.")


MAX_FAILED_COLLECTION_KEYS = 20
_MINUTE = timedelta(minutes=1)


def read_limit_exceeded(request: Request) -> str | None:
    """Rate-limit message when this visitor reads the public API too fast, else None.

    Only GET routes of the public API are counted (static files, the health probe and the
    admin area, which has its own authentication, are not). File exports have their own,
    stricter bucket because each one reads thousands of rows."""
    path = request.url.path
    if request.method != "GET" or not path.startswith("/api/v1/"):
        return None
    if path in ("/api/v1/health", "/api/v1/config") or path.startswith("/api/v1/admin"):
        return None
    client_id = request.client.host if request.client else "unknown"
    if path.startswith("/api/v1/export/") and not rate_limiter.allow(
        f"export:{client_id}", settings.export_rate_limit_per_minute, _MINUTE
    ):
        return "Too many file exports. Try again in a minute."
    if not rate_limiter.allow(f"read:{client_id}", settings.read_rate_limit_per_minute, _MINUTE):
        return "Too many requests. Try again in a minute."
    return None
