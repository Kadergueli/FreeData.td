"""Admin area: authentication, strategic overview with alerts, audit trail.

Sign-in is handled by Supabase Auth in the browser (e-mail + password). The backend never
sees the password: it receives the session's access token and asks Supabase who it belongs
to (works with any JWT signing scheme and needs no secret), then checks that the e-mail is an
administrator (ADMIN_EMAILS = permanent owners, plus the table_admins list).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.config import settings
from app.security import rate_limiter
from app.services.admin_store import AdminStore
from app.services.scheduler import scheduler_service
from app.services.storage import SECTOR_IDS, ObservationRepository, _cache_get, _cache_set

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_TOKEN_CACHE: dict[str, tuple[float, str | None]] = {}
_TOKEN_TTL = 60.0
_FAILED_AUTH_PER_HOUR = 30


@dataclass(frozen=True)
class AdminUser:
    email: str
    role: str  # "owner" | "admin"


def admin_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_anon_key)


def verify_access_token(token: str) -> str | None:
    """Ask Supabase Auth who owns this access token. Returns the confirmed e-mail or None."""
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    hit = _TOKEN_CACHE.get(key)
    if hit and now - hit[0] < _TOKEN_TTL:
        return hit[1]
    email: str | None = None
    try:
        resp = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key or "", "Authorization": f"Bearer {token}"},
            timeout=8.0,
        )
        if resp.status_code == 200:
            user = resp.json()
            if user.get("email") and user.get("email_confirmed_at"):
                email = str(user["email"]).strip().lower()
    except Exception as exc:
        logger.warning("Supabase Auth verification failed: %s", exc)
        raise HTTPException(status_code=503, detail="Authentication service unreachable.") from exc
    if len(_TOKEN_CACHE) > 500:
        _TOKEN_CACHE.clear()
    _TOKEN_CACHE[key] = (now, email)
    return email


def _store() -> AdminStore:
    from app.main import repository  # late import: main imports this module
    return AdminStore(repository)


def require_admin(request: Request) -> AdminUser:
    if not admin_configured():
        raise HTTPException(status_code=503, detail="Admin area is not configured on this server.")
    client = request.client.host if request.client else "unknown"
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required.")

    email = verify_access_token(token)
    if not email:
        if not rate_limiter.allow(f"admin-auth-fail:{client}", _FAILED_AUTH_PER_HOUR):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    if email in settings.owner_emails:
        return AdminUser(email, "owner")
    role = _store().get_role(email)
    if not role:
        if not rate_limiter.allow(f"admin-auth-fail:{client}", _FAILED_AUTH_PER_HOUR):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
        raise HTTPException(status_code=403, detail="This account is not an administrator.")
    return AdminUser(email, role)


def require_owner(admin: AdminUser = Depends(require_admin)) -> AdminUser:
    if admin.role != "owner":
        raise HTTPException(status_code=403, detail="Owner role required.")
    return admin


# ── Strategic overview ────────────────────────────────────────────────────────

LEVELS = {"critical": 0, "warning": 1, "info": 2}


def _age_hours(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return (now - d).total_seconds() / 3600.0


def compute_alerts(
    *, stats: dict, sector_last: dict, scheduler: dict, audit: dict, llm_configured: bool, now: datetime,
) -> list[dict[str, Any]]:
    """Plain-rule alerts: each one says what is wrong, so the admin can act on it."""
    alerts: list[dict[str, Any]] = []

    def add(level: str, code: str, message: str, **params: Any) -> None:
        alerts.append({"level": level, "code": code, "message": message, "params": params})

    sectors = stats.get("sectors") or {}
    if not sectors:
        add("critical", "data_unreadable", "Observation counts could not be read from the database.")
    for sec in SECTOR_IDS:
        if sec in sectors and sectors[sec] == 0:
            add("warning", "sector_empty", f"Sector '{sec}' has no published data.", sector=sec)

    age = _age_hours(stats.get("last_update"), now)
    if sectors and age is None:
        add("warning", "never_published", "No publication date is available.")
    elif age is not None and age > 24 * 7:
        add("critical", "collection_stalled", f"Nothing was published for {int(age // 24)} days: collection has stopped.", days=int(age // 24))
    elif age is not None and age > 48:
        add("warning", "collection_late", f"Last publication was {int(age // 24)} day(s) ago.", days=int(age // 24))

    for sec in SECTOR_IDS:
        if sectors.get(sec, 0) > 0:
            sec_age = _age_hours(sector_last.get(sec), now)
            if sec_age is not None and sec_age > 24 * 14:
                add("warning", "sector_not_collected", f"Sector '{sec}' was not refreshed for {int(sec_age // 24)} days.", sector=sec, days=int(sec_age // 24))

    last_result = scheduler.get("last_result") or {}
    for sec, res in (last_result.get("sectors") or {}).items():
        if isinstance(res, dict) and res.get("error"):
            add("warning", "harvest_error", f"The last harvest failed for '{sec}': {res['error']}", sector=sec, error=str(res["error"])[:200])
    if scheduler.get("last_run") is None:
        add("info", "scheduler_idle", "No in-process harvest since this server started (the daily GitHub workflow is the main trigger).")

    if (audit.get("nb_anomalies") or 0) > 0:
        add("info", "anomalies", f"{audit['nb_anomalies']} validation anomalies are on record.", count=audit["nb_anomalies"])
    if not llm_configured:
        add("info", "llm_missing", "GROQ_API_KEY is not set: reports use the statistical fallback instead of the language model.")

    alerts.sort(key=lambda a: LEVELS.get(a["level"], 9))
    return alerts


def build_overview(repository: ObservationRepository, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    stats = repository.get_stats()
    sector_last = repository.get_sector_last_update()
    audit = (repository.get_pipeline_audit() or {}).get("reports_summary") or {}
    scheduler = scheduler_service.get_status()
    alerts = compute_alerts(
        stats=stats, sector_last=sector_last, scheduler=scheduler, audit=audit,
        llm_configured=bool(settings.groq_api_key), now=now,
    )
    sectors = [
        {"id": sec, "count": (stats.get("sectors") or {}).get(sec), "last_published": sector_last.get(sec)}
        for sec in SECTOR_IDS
    ]
    return {
        "generated_at": now.isoformat(),
        "service": {"storage_backend": repository.backend, "scheduler": scheduler},
        "data": {
            "total": stats.get("total"),
            "last_update": stats.get("last_update"),
            "regions_covered": len(stats.get("regions") or {}),
            "sectors": sectors,
        },
        "quality": {
            "score_global": audit.get("score_global"),
            "anomalies": audit.get("nb_anomalies"),
            "total_raw": audit.get("total_raw"),
            "total_clean": audit.get("total_clean"),
            "total_public": audit.get("total_public"),
        },
        "alerts": alerts,
        "health": "critical" if any(a["level"] == "critical" for a in alerts)
        else "warning" if any(a["level"] == "warning" for a in alerts) else "ok",
    }


@router.post("/session")
def start_session(admin: AdminUser = Depends(require_admin)) -> dict:
    """Called once right after sign-in: records the login and returns the admin's identity."""
    _store().log(admin.email, "login")
    return {"email": admin.email, "role": admin.role}


@router.get("/me")
def me(admin: AdminUser = Depends(require_admin)) -> dict:
    return {"email": admin.email, "role": admin.role}


@router.get("/overview")
def overview(admin: AdminUser = Depends(require_admin)) -> dict:
    from app.main import repository
    cached = _cache_get("admin_overview", 20.0)
    if cached is not None:
        return cached
    result = build_overview(repository)
    _cache_set("admin_overview", result)
    return result


@router.get("/audit-log")
def audit_log(limit: int = Query(default=100, ge=1, le=500), admin: AdminUser = Depends(require_admin)) -> dict:
    return {"entries": _store().list_audit(limit)}


# ── Collections: history + manual runs ───────────────────────────────────────

class RunRequest(BaseModel):
    sectors: list[str] | None = None  # None / empty = every sector


@router.get("/collections")
def collections(limit: int = Query(default=30, ge=1, le=100), admin: AdminUser = Depends(require_admin)) -> dict:
    status = scheduler_service.get_status()
    try:
        runs = scheduler_service.history.list_runs(limit)
    except Exception as exc:
        logger.error("harvest history unreadable: %s", exc)
        raise HTTPException(status_code=503, detail="Harvest history could not be read from the database.") from exc
    return {
        "sector_ids": list(SECTOR_IDS),
        "job_running": status["job_running"],
        "current_run": status.get("current_run"),
        "next_run": status.get("next_run"),
        "runs": runs,
    }


@router.post("/collections/run", status_code=202)
async def run_collection(body: RunRequest | None = None, admin: AdminUser = Depends(require_admin)) -> dict:
    sectors = list(dict.fromkeys(body.sectors)) if body and body.sectors else None
    try:
        started = scheduler_service.start_background_job(sectors, trigger="admin", triggered_by=admin.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if started:
        await asyncio.to_thread(
            _store().log, admin.email, "harvest_run", ",".join(sectors) if sectors else "all",
            {"sectors": sectors or list(SECTOR_IDS)},
        )
        _cache_set("admin_overview", None)
    return {"status": "started" if started else "already_running"}
