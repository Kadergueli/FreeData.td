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

    def allow(self, client_id: str, limit: int) -> bool:
        now = datetime.now(UTC)
        threshold = now - timedelta(hours=1)
        with self._lock:
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


def require_collection_rate_limit(request: Request) -> None:
    """Rate-limit data-collection runs per IP — no secret key.

    Used only for the sectors actually wired to a public frontend button
    (agriculture/environment/markets/economy — see data.js and home.js). Same
    reasoning as require_analysis_rate_limit: a public button can't hold a
    secret without exposing it to every visitor, so rate limiting is the
    honest protection here.
    """
    client_id = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(f"collection:{client_id}", settings.collection_rate_limit_per_hour):
        raise HTTPException(status_code=429, detail="Collection rate limit reached. Try again later.")


def require_collection_access(request: Request, x_collection_key: str | None = Header(default=None)) -> None:
    """Require a server-side secret and limit manual/triggered data-collection runs.

    Reserved for endpoints NOT wired to any public UI button (transport,
    education, and the scheduled-harvest trigger) — these are admin/ops tools,
    so a secret key is an appropriate, non-conflicting protection.
    """
    if not settings.collection_api_key:
        raise HTTPException(status_code=503, detail="COLLECTION_API_KEY is not configured on the server.")
    if not x_collection_key or not compare_digest(x_collection_key, settings.collection_api_key):
        raise HTTPException(status_code=401, detail="A valid X-Collection-Key is required.")
    client_id = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(f"collection-admin:{client_id}", settings.collection_rate_limit_per_hour):
        raise HTTPException(status_code=429, detail="Collection rate limit reached. Try again later.")
