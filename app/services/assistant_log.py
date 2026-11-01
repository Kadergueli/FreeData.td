"""Journal des questions posées à l'assistant (Supabase si configuré, SQLite en développement).

Écriture « au mieux » : un échec du journal ne doit jamais faire échouer une réponse. Les questions sont
limitées à 300 caractères et conservées RETENTION_DAYS jours."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.storage import ObservationRepository, _with_retry

logger = logging.getLogger(__name__)

RETENTION_DAYS = 180
UNDERSTOOD = {"price", "prices", "compare", "trend", "ranking", "weather"}
NOT_UNDERSTOOD = {"help", "ask_product", "ask_market", "ask_place"}      # il a fallu reposer la question
COLUMNS = "id,created_at,channel,user_ref,question,intent,lens,refused,corrected,followup,latency_ms,feedback"


class AssistantLog:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @property
    def _sb(self):
        return self.repository._supabase

    def _sqlite(self):
        c = self.repository._connection()
        c.execute("""CREATE TABLE IF NOT EXISTS assistant_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, channel TEXT NOT NULL DEFAULT 'admin',
            user_ref TEXT, question TEXT NOT NULL, intent TEXT NOT NULL, lens TEXT, refused INTEGER NOT NULL DEFAULT 0,
            corrected INTEGER NOT NULL DEFAULT 0, followup INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER, feedback INTEGER)""")
        return c

    def record(self, *, question: str, answer: dict[str, Any], user_ref: str | None, channel: str = "admin",
               latency_ms: int | None = None) -> int | None:
        row = {
            "channel": channel, "user_ref": user_ref, "question": (question or "").strip()[:300],
            "intent": str(answer.get("intent") or "unknown"), "lens": answer.get("lens"),
            "refused": bool(answer.get("refused")), "corrected": bool((answer.get("data") or {}).get("corrected")),
            "followup": bool((answer.get("data") or {}).get("followup")), "latency_ms": latency_ms,
        }
        try:
            if self._sb:
                res = _with_retry(lambda: self._sb.table("table_assistant_log").insert(row).execute(), attempts=2,
                                  label="assistant log insert")
                return (res.data or [{}])[0].get("id")
            with self._sqlite() as c:
                cur = c.execute(
                    "INSERT INTO assistant_log (created_at, channel, user_ref, question, intent, lens, refused, corrected, followup, latency_ms)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (datetime.now(UTC).isoformat(), row["channel"], row["user_ref"], row["question"], row["intent"], row["lens"],
                     int(row["refused"]), int(row["corrected"]), int(row["followup"]), row["latency_ms"]))
                return cur.lastrowid
        except Exception as exc:
            logger.warning("assistant log write failed: %s", exc)
            return None

    def set_feedback(self, log_id: int, value: int, user_ref: str | None) -> bool:
        if value not in (-1, 1):
            raise ValueError("feedback must be -1 or 1")
        try:
            if self._sb:
                res = self._sb.table("table_assistant_log").update({"feedback": value}).eq("id", log_id).execute()
                return bool(res.data)
            with self._sqlite() as c:
                return c.execute("UPDATE assistant_log SET feedback = ? WHERE id = ?", (value, log_id)).rowcount > 0
        except Exception as exc:
            logger.warning("assistant feedback failed: %s", exc)
            return False

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        since = (datetime.now(UTC) - timedelta(days=RETENTION_DAYS)).isoformat()
        if self._sb:
            rows = self._sb.table("table_assistant_log").select(COLUMNS).gte("created_at", since) \
                .order("created_at", desc=True).limit(limit).execute().data
            return list(rows or [])
        with self._sqlite() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM assistant_log WHERE created_at >= ? ORDER BY id DESC LIMIT ?", (since, limit))]

    def purge(self) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=RETENTION_DAYS)).isoformat()
        try:
            if self._sb:
                self._sb.table("table_assistant_log").delete().lt("created_at", cutoff).execute()
            else:
                with self._sqlite() as c:
                    c.execute("DELETE FROM assistant_log WHERE created_at < ?", (cutoff,))
        except Exception as exc:
            logger.warning("assistant log purge failed: %s", exc)

    def summary(self, limit: int = 500) -> dict[str, Any]:
        rows = self.recent(limit)
        intents = Counter(r["intent"] for r in rows)
        total = len(rows)
        answered = sum(n for i, n in intents.items() if i in UNDERSTOOD)
        voted = [r["feedback"] for r in rows if r.get("feedback") in (-1, 1)]
        to_improve: Counter = Counter()
        for r in rows:
            if r["intent"] in NOT_UNDERSTOOD | {"no_data", "unavailable"} or r.get("feedback") == -1:
                to_improve[(r["question"].strip().lower(), r["intent"])] += 1
        times = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
        median_ms = times[len(times) // 2] if times else None
        return {
            "total": total, "answered": answered,
            "answered_pct": round(100 * answered / total, 1) if total else None,
            "refused": sum(1 for r in rows if r["refused"]),
            "corrected": sum(1 for r in rows if r["corrected"]),
            "followups": sum(1 for r in rows if r["followup"]),
            "helpful": sum(1 for v in voted if v == 1), "not_helpful": sum(1 for v in voted if v == -1),
            "median_ms": median_ms,
            "by_intent": [{"intent": i, "count": n} for i, n in intents.most_common()],
            "to_improve": [{"question": q, "intent": i, "count": n} for (q, i), n in to_improve.most_common(15)],
            "recent": rows[:30],
        }
