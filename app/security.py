from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from threading import Lock

from fastapi import Header, HTTPException, Request

from app.config import settings


class AnalysisRateLimiter:
    """In-memory rate limiter for the costly LLM endpoint."""

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


analysis_rate_limiter = AnalysisRateLimiter()


def require_analysis_access(request: Request, x_analysis_key: str | None = Header(default=None)) -> None:
    """Require a server-side secret and limit study generation."""
    if not settings.analysis_api_key:
        raise HTTPException(status_code=503, detail="ANALYSIS_API_KEY is not configured on the server.")
    if not x_analysis_key or not compare_digest(x_analysis_key, settings.analysis_api_key):
        raise HTTPException(status_code=401, detail="A valid X-Analysis-Key is required.")
    client_id = request.client.host if request.client else "unknown"
    if not analysis_rate_limiter.allow(client_id, settings.analysis_rate_limit_per_hour):
        raise HTTPException(status_code=429, detail="Study-generation rate limit reached. Try again later.")
