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
from pydantic import BaseModel, Field

from app.config import settings
from app.security import rate_limiter
from app.services.admin_store import AdminStore
from app.services.cadence import cadence_days
from app.services.data_admin import DataAdminStore
from app.services.quarantine import STATUSES as QUARANTINE_STATUSES
from app.services.quarantine import QuarantineStore
from app.services.scheduler import scheduler_service
from app.services.storage import SECTOR_IDS, ObservationRepository, _cache_get, _cache_set, invalidate_cache

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
    quarantine_pending: int = 0, stale_sources: list[dict[str, Any]] | None = None,
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
            # A monthly sector is refreshed once a month: alert after two missed rhythms.
            if sec_age is not None and sec_age > 24 * max(14, 2 * cadence_days(sec)):
                add("warning", "sector_not_collected", f"Sector '{sec}' was not refreshed for {int(sec_age // 24)} days.", sector=sec, days=int(sec_age // 24))

    last_result = scheduler.get("last_result") or {}
    for sec, res in (last_result.get("sectors") or {}).items():
        if isinstance(res, dict) and res.get("error"):
            add("warning", "harvest_error", f"The last harvest failed for '{sec}': {res['error']}", sector=sec, error=str(res["error"])[:200])
    if scheduler.get("last_run") is None:
        add("info", "scheduler_idle", "No in-process harvest since this server started (the daily GitHub workflow is the main trigger).")

    for src in stale_sources or []:
        add("warning", "source_stale",
            f"Source '{src['source']}' ({src['sector']}) has no data newer than {src['latest_reference']} "
            f"({src['age_days']} days; normal is {src['max_age_days']}).",
            sector=src["sector"], source=src["source"], date=src["latest_reference"], days=src["age_days"])
    if quarantine_pending > 0:
        add("warning", "quarantine_pending", f"{quarantine_pending} suspicious value(s) are held back and await your review.", count=quarantine_pending)
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
    try:
        quarantine = QuarantineStore(repository).counts()
    except Exception as exc:  # table missing / DB hiccup: the overview must still load
        logger.warning("quarantine counts unreadable: %s", exc)
        quarantine = None
    try:
        stale_sources = [s for s in repository.source_freshness() if s["status"] == "stale"]
    except Exception as exc:  # the overview must still load
        logger.warning("source freshness unreadable: %s", exc)
        stale_sources = []
    alerts = compute_alerts(
        stats=stats, sector_last=sector_last, scheduler=scheduler, audit=audit,
        llm_configured=bool(settings.groq_api_key), now=now,
        quarantine_pending=(quarantine or {}).get("pending", 0), stale_sources=stale_sources,
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
        "quarantine": quarantine,
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


# ── Quarantine: review of suspicious values ──────────────────────────────────

class ReviewBody(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class CorrectBody(ReviewBody):
    value: float


def _quarantine() -> QuarantineStore:
    from app.main import repository
    return QuarantineStore(repository)


def _label(rec: dict[str, Any]) -> str:
    return f"{rec['secteur']}/{rec['indicateur']}/{rec['date_reference']}/{rec['region']}"


@router.get("/quarantine")
def quarantine_list(
    status: str = Query(default="pending"), limit: int = Query(default=100, ge=1, le=500),
    admin: AdminUser = Depends(require_admin),
) -> dict:
    if status != "all" and status not in QUARANTINE_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    store = _quarantine()
    try:
        return {"items": store.list(status, limit), "counts": store.counts()}
    except Exception as exc:
        logger.error("quarantine unreadable: %s", exc)
        raise HTTPException(status_code=503, detail="The quarantine could not be read from the database.") from exc


async def _review(qid: int, kind: str, admin: AdminUser, note: str | None, value: float | None = None) -> dict:
    from app.main import repository
    store = QuarantineStore(repository)
    rec = await asyncio.to_thread(store.get, qid)
    if rec is None:
        raise HTTPException(status_code=404, detail="No such quarantined value.")
    if rec["status"] != "pending":
        raise HTTPException(status_code=409, detail="This value was already reviewed.")
    note = (note or "").strip() or None
    new_value = float(rec["valeur"]) if kind == "approved" else value
    # Claim the row first (atomic pending -> decided) so two admins cannot both act on it.
    if not await asyncio.to_thread(store.decide, qid, kind, admin.email, note, value if kind == "corrected" else None):
        raise HTTPException(status_code=409, detail="This value was already reviewed.")
    if kind != "rejected":
        extra = None
        if kind == "corrected":
            extra = f"[Valeur corrigée par un administrateur : {rec['valeur']:g} -> {new_value:g}]"
        try:
            await asyncio.to_thread(repository.publish_reviewed, rec, new_value, admin.email, extra)
        except Exception as exc:
            await asyncio.to_thread(store.reopen, qid)
            logger.error("publishing reviewed value %s failed: %s", qid, exc)
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            raise HTTPException(status_code=503, detail="Publishing failed; the value is back in the queue.") from exc
    await asyncio.to_thread(
        _store().log, admin.email, f"quarantine_{kind}", _label(rec),
        {"id": qid, "original": rec["valeur"], "published": new_value if kind != "rejected" else None, "note": note},
    )
    invalidate_cache()
    _cache_set("admin_overview", None)
    return {"status": kind, "id": qid}


@router.post("/quarantine/{qid}/approve")
async def quarantine_approve(qid: int, body: ReviewBody | None = None, admin: AdminUser = Depends(require_admin)) -> dict:
    return await _review(qid, "approved", admin, body.note if body else None)


@router.post("/quarantine/{qid}/correct")
async def quarantine_correct(qid: int, body: CorrectBody, admin: AdminUser = Depends(require_admin)) -> dict:
    return await _review(qid, "corrected", admin, body.note, body.value)


@router.post("/quarantine/{qid}/reject")
async def quarantine_reject(qid: int, body: ReviewBody | None = None, admin: AdminUser = Depends(require_admin)) -> dict:
    return await _review(qid, "rejected", admin, body.note if body else None)


# ── Published data: find, correct, delete (archived), restore ───────────────

def _reason(raw: str) -> str:
    text = (raw or "").strip()
    if len(text) < 3:
        raise ValueError("A reason (3 characters or more) is required.")
    return text[:300]


class DataCorrectBody(BaseModel):
    value: float
    reason: str = Field(max_length=300)


class DataDeleteBody(BaseModel):
    reason: str = Field(max_length=300)


def _data() -> DataAdminStore:
    from app.main import repository
    return DataAdminStore(repository)


def _obs_label(o: dict[str, Any]) -> str:
    return f"{o['sector']}/{o['indicator']}/{o['reference_date']}/{o['region']}"


def _after_data_change() -> None:
    invalidate_cache()
    _cache_set("admin_overview", None)


@router.get("/data")
async def data_search(
    sector: str | None = Query(default=None), q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200), admin: AdminUser = Depends(require_admin),
) -> dict:
    if sector and sector not in SECTOR_IDS:
        raise HTTPException(status_code=422, detail="Unknown sector.")
    try:
        return {"items": await asyncio.to_thread(_data().search, sector, q, limit)}
    except Exception as exc:
        logger.error("data search failed: %s", exc)
        raise HTTPException(status_code=503, detail="Published data could not be read from the database.") from exc


@router.post("/data/{oid}/correct")
async def data_correct(oid: int, body: DataCorrectBody, admin: AdminUser = Depends(require_admin)) -> dict:
    try:
        reason = _reason(body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _data()
    try:
        before = await asyncio.to_thread(store.correct, oid, body.value, admin.email, reason)
    except Exception as exc:
        logger.error("data correct failed: %s", exc)
        raise HTTPException(status_code=503, detail="The correction could not be saved; nothing was changed.") from exc
    if before is None:
        raise HTTPException(status_code=404, detail="No such published value.")
    await asyncio.to_thread(_store().log, admin.email, "data_corrected", _obs_label(before),
                            {"id": oid, "before": before["value"], "after": body.value, "reason": reason})
    _after_data_change()
    return {"status": "corrected", "id": oid}


@router.post("/data/{oid}/delete")
async def data_delete(oid: int, body: DataDeleteBody, admin: AdminUser = Depends(require_admin)) -> dict:
    try:
        reason = _reason(body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _data()
    try:
        row = await asyncio.to_thread(store.delete, oid, admin.email, reason)
    except Exception as exc:
        logger.error("data delete failed: %s", exc)
        raise HTTPException(status_code=503, detail="The deletion could not be completed.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="No such published value.")
    await asyncio.to_thread(_store().log, admin.email, "data_deleted", _obs_label(row),
                            {"id": oid, "value": row["value"], "reason": reason})
    _after_data_change()
    return {"status": "deleted", "id": oid}


@router.get("/data/deleted")
async def data_deleted(limit: int = Query(default=50, ge=1, le=200), admin: AdminUser = Depends(require_admin)) -> dict:
    try:
        return {"items": await asyncio.to_thread(_data().list_deleted, limit)}
    except Exception as exc:
        logger.error("deleted archive unreadable: %s", exc)
        raise HTTPException(status_code=503, detail="The archive of deleted values could not be read.") from exc


@router.post("/data/deleted/{aid}/restore")
async def data_restore(aid: int, admin: AdminUser = Depends(require_admin)) -> dict:
    store = _data()
    try:
        row = await asyncio.to_thread(store.restore, aid, admin.email)
    except Exception as exc:
        logger.error("data restore failed: %s", exc)
        raise HTTPException(status_code=503, detail="The value could not be restored.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Nothing to restore (unknown or already restored).")
    await asyncio.to_thread(_store().log, admin.email, "data_restored", _obs_label(row), {"archive_id": aid, "value": row["value"]})
    _after_data_change()
    return {"status": "restored", "id": aid}


# ── Reports (AI studies) ─────────────────────────────────────────────────────

@router.get("/reports")
async def reports_list(limit: int = Query(default=50, ge=1, le=200), admin: AdminUser = Depends(require_admin)) -> dict:
    from app.main import repository
    try:
        return {"items": await asyncio.to_thread(repository.list_studies, None, limit)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Reports could not be read.") from exc


@router.post("/reports/{rid}/delete")
async def reports_delete(rid: int, body: DataDeleteBody, admin: AdminUser = Depends(require_admin)) -> dict:
    from app.main import repository
    try:
        reason = _reason(body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        deleted = await asyncio.to_thread(repository.delete_study, rid)
    except Exception as exc:
        logger.error("report delete failed: %s", exc)
        raise HTTPException(status_code=503, detail="The report could not be deleted.") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="No such report.")
    await asyncio.to_thread(_store().log, admin.email, "report_deleted", f"report:{rid}", {"reason": reason})
    return {"status": "deleted", "id": rid}


# ── Team (owner only) ────────────────────────────────────────────────────────

class AdminEmailBody(BaseModel):
    email: str = Field(max_length=254)


def _clean_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email or email.count("@") != 1 or len(email) > 254:
        raise HTTPException(status_code=422, detail="Enter a valid e-mail address.")
    return email


@router.get("/admins")
async def admins_list(admin: AdminUser = Depends(require_admin)) -> dict:
    stored = await asyncio.to_thread(_store().list_admins)
    owners = settings.owner_emails
    team = [{"email": e, "role": "owner", "permanent": True} for e in sorted(owners)]
    team += [{"email": a["email"], "role": a["role"], "permanent": False, "added_by": a.get("added_by"),
              "created_at": a.get("created_at")} for a in stored if a["email"] not in owners]
    return {"admins": team, "can_manage": admin.role == "owner"}


@router.post("/admins", status_code=201)
async def admins_add(body: AdminEmailBody, owner: AdminUser = Depends(require_owner)) -> dict:
    email = _clean_email(body.email)
    if email in settings.owner_emails:
        raise HTTPException(status_code=409, detail="This person is already a permanent owner.")
    try:
        await asyncio.to_thread(_store().add_admin, email, "admin", owner.email)
    except Exception as exc:
        logger.error("add admin failed: %s", exc)
        raise HTTPException(status_code=503, detail="The administrator could not be added.") from exc
    await asyncio.to_thread(_store().log, owner.email, "admin_added", email, {})
    return {"status": "added", "email": email}


@router.post("/admins/remove")
async def admins_remove(body: AdminEmailBody, owner: AdminUser = Depends(require_owner)) -> dict:
    email = _clean_email(body.email)
    if email in settings.owner_emails:
        raise HTTPException(status_code=409, detail="A permanent owner cannot be removed here (it is set in ADMIN_EMAILS).")
    if email == owner.email:
        raise HTTPException(status_code=409, detail="You cannot remove yourself.")
    try:
        removed = await asyncio.to_thread(_store().remove_admin, email)
    except Exception as exc:
        logger.error("remove admin failed: %s", exc)
        raise HTTPException(status_code=503, detail="The administrator could not be removed.") from exc
    if not removed:
        raise HTTPException(status_code=404, detail="No such administrator.")
    await asyncio.to_thread(_store().log, owner.email, "admin_removed", email, {})
    return {"status": "removed", "email": email}
