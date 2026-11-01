"""WhatsApp channel (Meta Cloud API) for the data assistant.

GET  /api/v1/whatsapp/webhook  -> Meta's one-time verification handshake.
POST /api/v1/whatsapp/webhook  -> incoming messages. The signature is checked FIRST; the answer is sent in the
                                  background so Meta always gets its 200 within a second (it retries otherwise).

Privacy: a phone number is never stored. Only a salted HMAC (16 hex chars) identifies a person, which is enough
for the daily limit and for the follow-up context. Everything else is the same question log as the admin tab."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.security import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

CONTEXT_TTL = 30 * 60            # follow-ups ("et à Dembé ?") are understood for 30 minutes
MAX_CONTEXTS = 2000
MAX_SEEN = 4000
MAX_REPLY_CHARS = 1500
ABUSE_LIMIT = 5                  # refused messages per 24 h before the number is ignored

FIRST_CONTACT = ("Bienvenue sur FreeData.td 👋 Vos messages sont enregistrés sans votre numéro (un code anonyme seulement) "
                 "pour améliorer le service, et supprimés après 6 mois.\n\n")
NOT_TEXT = ("Pour l'instant, je comprends seulement les messages écrits. Posez-moi votre question par écrit, "
            "par exemple : « Prix du mil à Abéché ».")
LIMIT_REACHED = ("Vous avez atteint la limite de questions pour aujourd'hui ({n}). Revenez demain : "
                 "vous pourrez de nouveau me demander les prix des marchés et la météo.")

_lock = threading.Lock()
_last_event: dict[str, Any] = {}       # what Meta's last call to us led to (memory only; shown in the admin)
_contexts: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
_seen: "OrderedDict[str, float]" = OrderedDict()


def enabled() -> bool:
    return bool(settings.whatsapp_app_secret and settings.whatsapp_access_token and settings.whatsapp_phone_number_id)


def record_event(kind: str, detail: str | None = None) -> None:
    """kind: verified | verify_failed | messages | no_message | bad_signature | not_configured | bad_payload
    | replied | send_failed.
    `detail` never contains a secret (only lengths / "not set"); it is shown to signed-in administrators only."""
    with _lock:
        _last_event.clear()
        _last_event.update(kind=kind, at=datetime.now(UTC).isoformat(), detail=detail)
    (logger.info if kind in ("verified", "messages", "no_message", "replied") else logger.warning)("whatsapp webhook: %s %s", kind, detail or "")


def last_event() -> dict[str, Any] | None:
    with _lock:
        return dict(_last_event) if _last_event else None


def clear_state() -> None:
    with _lock:
        _last_event.clear()
        _contexts.clear()
        _seen.clear()


# ── security helpers ───────────────────────────────────────────────────────
def verify_signature(body: bytes, header: str | None, secret: str | None) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app secret, raw body)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):].strip())


def person_ref(msg: dict[str, str]) -> str:
    """Stable anonymous code of the sender: the BSUID when Meta gives one (it survives a phone-number change),
    otherwise the phone number."""
    return phone_ref(msg.get("user_id") or msg.get("from") or "")


def phone_ref(number: str) -> str:
    """Salted, one-way code for a phone number (digits only) or a BSUID: same person -> same code, never reversible."""
    key = (settings.whatsapp_hash_salt or settings.whatsapp_app_secret or "freedata").encode()
    raw = (number or "").strip()
    ident = raw.lower() if re.search(r"[A-Za-z]", raw) else re.sub(r"\D", "", raw)    # BSUID keeps its letters
    return hmac.new(key, ident.encode(), hashlib.sha256).hexdigest()[:16]


# ── small in-memory state ──────────────────────────────────────────────────
def _first_time(message_id: str) -> bool:
    """False if Meta already delivered this message (it retries) — answers must never be sent twice."""
    now = time.monotonic()
    with _lock:
        if message_id in _seen:
            return False
        _seen[message_id] = now
        while len(_seen) > MAX_SEEN:
            _seen.popitem(last=False)
        return True


def get_context(ref: str) -> dict | None:
    with _lock:
        hit = _contexts.get(ref)
        if hit and time.monotonic() - hit[0] < CONTEXT_TTL:
            return hit[1]
        _contexts.pop(ref, None)
        return None


def set_context(ref: str, answer: dict[str, Any]) -> None:
    """Remember what the last answer was about, so that "et à Dembé ?" is understood (the server re-validates it)."""
    if not answer.get("lens"):
        return
    data = answer.get("data") or {}
    markets_list = data.get("markets")
    market = data.get("market") or (markets_list[0] if isinstance(markets_list, list) and markets_list else None)
    ctx = {"lens": answer["lens"], "product": data.get("product"), "market": market, "province": data.get("province")}
    with _lock:
        _contexts[ref] = (time.monotonic(), ctx)
        _contexts.move_to_end(ref)
        while len(_contexts) > MAX_CONTEXTS:
            _contexts.popitem(last=False)


# ── parsing ────────────────────────────────────────────────────────────────
def _items(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def extract_messages(payload: Any) -> list[dict[str, str]]:
    """[{from, user_id, id, type, text}] for every incoming user message; delivery statuses and malformed shapes
    are ignored.

    Meta now identifies people by a business-scoped user id (BSUID, e.g. "GH.4314..."): when a user has adopted a
    username the phone number can be missing from the message. So `from` (phone) and `user_id` (BSUID) are both
    optional, and at least one is required. The phone is also looked up in `contacts[].wa_id`."""
    out: list[dict[str, str]] = []
    for entry in _items(_dict(payload).get("entry")):
        for change in _items(_dict(entry).get("changes")):
            value = _dict(_dict(change).get("value"))
            contacts = [_dict(c) for c in _items(value.get("contacts"))]
            for msg in _items(value.get("messages")):
                msg = _dict(msg)
                bsuid = str(msg.get("from_user_id") or "")
                phone = str(msg.get("from") or "")
                if not phone:
                    for c in contacts:                      # same person, identified in the contacts block
                        if c.get("wa_id") and (not bsuid or str(c.get("user_id") or "") == bsuid):
                            phone = str(c["wa_id"])
                            break
                if not bsuid:
                    bsuid = next((str(c["user_id"]) for c in contacts if c.get("user_id") and str(c.get("wa_id") or "") == phone), "")
                if not (phone or bsuid) or not msg.get("id"):
                    continue
                kind = str(msg.get("type") or "")
                text = _dict(msg.get("text")).get("body") if kind == "text" else ""
                out.append({"from": phone, "user_id": bsuid, "id": str(msg["id"]), "type": kind,
                            "text": text if isinstance(text, str) else ""})
    return out


# ── sending (replaceable in tests / for another provider) ──────────────────
SEND_HINTS = {
    131030: "this person is not in the allowed recipients of the TEST number: Meta dashboard > WhatsApp > API Setup > step 1 "
            "'To' > Manage phone number list, add the number exactly as it is on WhatsApp (with country code) and confirm the code",
    131047: "more than 24 h since the person last wrote: they must send a new message first",
    131026: "message undeliverable (the number may not be on WhatsApp)",
    131056: "too many messages to this person in a short time: Meta throttles the pair",
    131009: "a parameter is invalid (check WHATSAPP_PHONE_NUMBER_ID)",
    100: "invalid parameter (check WHATSAPP_PHONE_NUMBER_ID, or a BSUID recipient on a test number)",
    190: "the access token is invalid or has expired: create a permanent token (system user) and update WHATSAPP_ACCESS_TOKEN",
    10: "the token lacks the whatsapp_business_messaging permission",
    200: "the token lacks the permission or the app is not linked to this WhatsApp account",
}


def _send_failure(status: int, text: str, via: str) -> str:
    """Short, secret-free explanation of a refused send (Meta's error code + message + a hint)."""
    try:
        err = (httpx.Response(status, text=text).json() or {}).get("error") or {}
    except ValueError:
        err = {}
    code = err.get("code")
    message = str(err.get("message") or text)[:160]
    hint = SEND_HINTS.get(code if isinstance(code, int) else -1)
    return f"Meta error {code if code is not None else status} (HTTP {status}, recipient by {via}): {message}" + (f" — {hint}" if hint else "")


async def send_text(to: str, body: str, recipient: str | None = None) -> None:
    """`to` = phone number; `recipient` = BSUID, used only when there is no phone number (never both)."""
    url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    payload: dict[str, Any] = {"messaging_product": "whatsapp", "type": "text", "text": {"body": body[:4000], "preview_url": False}}
    if to:
        payload["to"] = to
    else:
        payload["recipient"] = recipient
    via = "phone number" if to else "BSUID"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"})
    if res.status_code >= 400:
        record_event("send_failed", _send_failure(res.status_code, res.text, via))
    else:
        record_event("replied", f"answer delivered to Meta (recipient by {via})")


sender = send_text


def _trim(text: str) -> str:
    """WhatsApp bubbles stay readable: cut at the last sentence end before the limit."""
    if len(text) <= MAX_REPLY_CHARS:
        return text
    cut = text[:MAX_REPLY_CHARS]
    end = max(cut.rfind(". "), cut.rfind("\n"))
    return (cut[:end] if end > 600 else cut).rstrip() + "…"


# ── one incoming message ───────────────────────────────────────────────────
def build_reply(msg: dict[str, str]) -> str | None:
    """The text to send back (None = stay silent). Runs in a worker thread: it touches the database."""
    from app.assistant import Assistant
    from app.main import repository
    from app.services.assistant_log import AssistantLog

    ref = person_ref(msg)
    log = AssistantLog(repository)
    started = time.perf_counter()
    try:
        if log.count_since(ref, 24, refused_only=True) >= ABUSE_LIMIT:
            return None                                              # insistent abuse: no more answers today
        used = log.count_since(ref, 24)
        if used >= settings.whatsapp_daily_limit:
            if used == settings.whatsapp_daily_limit:                # tell the person once, then stay quiet
                log.record(question="(limite atteinte)", answer={"intent": "rate_limited", "refused": True},
                           user_ref=ref, channel="whatsapp")
                return LIMIT_REACHED.format(n=settings.whatsapp_daily_limit)
            return None
        newcomer = not log.has_any(ref)
    except Exception as exc:                                         # the log must never silence the assistant
        logger.warning("whatsapp counters unavailable: %s", exc)
        newcomer = False

    if msg["type"] != "text" or not msg["text"].strip():
        answer = {"text": NOT_TEXT, "intent": "not_text", "lens": None, "refused": False, "data": {}}
        question = f"({msg['type'] or 'message'})"
    else:
        question = msg["text"]
        answer = Assistant(repository).answer(question, get_context(ref)).to_dict()
        set_context(ref, answer)
    log.record(question=question, answer=answer, user_ref=ref, channel="whatsapp",
               latency_ms=int((time.perf_counter() - started) * 1000))
    return _trim((FIRST_CONTACT if newcomer else "") + answer["text"])


async def handle_message(msg: dict[str, str]) -> None:
    try:
        reply = await asyncio.to_thread(build_reply, msg)
        if reply:
            if msg["from"]:
                await sender(msg["from"], reply)
            else:
                await sender("", reply, recipient=msg["user_id"])
    except Exception as exc:                                         # background task: never raise
        logger.exception("whatsapp message handling failed: %s", exc)


# ── routes ─────────────────────────────────────────────────────────────────
@router.get("/webhook")
def verify(mode: str = Query(default="", alias="hub.mode"), token: str = Query(default="", alias="hub.verify_token"),
           challenge: str = Query(default="", alias="hub.challenge")) -> PlainTextResponse:
    expected = settings.whatsapp_verify_token
    received = token.strip()
    if mode == "subscribe" and expected and hmac.compare_digest(received.encode(), expected.encode()):
        record_event("verified")
        return PlainTextResponse(challenge)
    if not expected:
        detail = "WHATSAPP_VERIFY_TOKEN is not set on the server (name misspelled, or the service was not redeployed)"
    elif mode != "subscribe":
        detail = f"unexpected hub.mode {mode!r}"
    elif not received:
        detail = "no hub.verify_token received"
    else:
        detail = f"token differs: the server expects {len(expected)} characters, Meta sent {len(received)}"
    record_event("verify_failed", detail)
    raise HTTPException(status_code=403, detail="Verification failed.")


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> dict:
    if not enabled():
        record_event("not_configured")
        raise HTTPException(status_code=503, detail="WhatsApp is not configured.")
    body = await request.body()
    if len(body) > 200_000:
        raise HTTPException(status_code=413, detail="Payload too large.")
    if not verify_signature(body, request.headers.get("x-hub-signature-256"), settings.whatsapp_app_secret):
        record_event("bad_signature")      # almost always: WHATSAPP_APP_SECRET differs from the app's secret
        raise HTTPException(status_code=403, detail="Invalid signature.")
    try:
        payload = await request.json()
    except ValueError:
        record_event("bad_payload")
        return {"status": "ignored"}
    incoming = extract_messages(payload)[:10]
    record_event("messages" if incoming else "no_message")
    for msg in incoming:
        if not rate_limiter.allow(f"wa-burst:{person_ref(msg)}", 20, window=timedelta(minutes=1)):
            continue                                                  # flood protection (20 / minute / number)
        if _first_time(msg["id"]):
            background.add_task(handle_message, msg)
    return {"status": "ok"}
