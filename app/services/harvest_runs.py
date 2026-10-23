"""Durable history of harvests, so the admin can see what ran, when, and what failed even
after the server restarted (the in-memory scheduler status is lost on every restart).

Supabase when configured (table_harvest_runs — see supabase/harvest_runs_setup.sql),
SQLite otherwise (development). Recording is best-effort: a history failure must never
break or hide a harvest."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.storage import ObservationRepository, _with_retry

logger = logging.getLogger(__name__)

TRIGGERS = ("scheduler", "api", "admin")


def summarize_results(sectors: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Reduce per-sector agent results to a compact summary and an overall status.

    A sector that raised, or whose sources reported errors, counts as a problem:
    all sectors failing -> 'failed'; some -> 'partial'; none -> 'completed'."""
    summary: dict[str, Any] = {}
    problems = failures = 0
    for name, res in (sectors or {}).items():
        res = res if isinstance(res, dict) else {}
        errors = [str(e)[:200] for e in (res.get("errors") or [])][:5]
        if res.get("error"):
            summary[name] = {"stored": 0, "error": str(res["error"])[:300]}
            problems += 1
            failures += 1
        else:
            summary[name] = {
                "stored": int(res.get("stored") or 0),
                "received": int(res.get("received") or 0),
                "rejected": int(res.get("rejected") or 0),
            }
            if errors:
                summary[name]["errors"] = errors
                problems += 1
    if not summary:
        return "completed", summary
    if failures == len(summary):
        return "failed", summary
    return ("partial" if problems else "completed"), summary


class HarvestRunStore:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @property
    def _sb(self):
        return self.repository._supabase

    def _sqlite(self):
        c = self.repository._connection()
        c.execute(
            """CREATE TABLE IF NOT EXISTS harvest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
                trigger TEXT NOT NULL, triggered_by TEXT, sectors TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL, total_stored INTEGER NOT NULL DEFAULT 0, results TEXT NOT NULL DEFAULT '{}')"""
        )
        return c

    def start(self, trigger: str, sectors: list[str], triggered_by: str | None) -> int | None:
        """Record a run as 'running'. Returns its id, or None if history is unavailable."""
        try:
            if self._sb:
                row = _with_retry(
                    lambda: self._sb.table("table_harvest_runs").insert(
                        {"trigger": trigger, "triggered_by": triggered_by, "sectors": sectors, "status": "running"}
                    ).execute(),
                    attempts=2, label="harvest_run start",
                ).data
                return int(row[0]["id"]) if row else None
            with self._sqlite() as c:
                cur = c.execute(
                    "INSERT INTO harvest_runs (started_at, trigger, triggered_by, sectors, status) VALUES (?,?,?,?,'running')",
                    (datetime.now(UTC).isoformat(), trigger, triggered_by, json.dumps(sectors)),
                )
                return cur.lastrowid
        except Exception as exc:
            logger.error("harvest history: could not record start: %s", exc)
            return None

    def finish(self, run_id: int | None, status: str, total_stored: int, results: dict[str, Any]) -> None:
        if run_id is None:
            return
        finished = datetime.now(UTC).isoformat()
        try:
            if self._sb:
                _with_retry(
                    lambda: self._sb.table("table_harvest_runs").update(
                        {"finished_at": finished, "status": status, "total_stored": total_stored, "results": results}
                    ).eq("id", run_id).execute(),
                    attempts=2, label="harvest_run finish",
                )
                return
            with self._sqlite() as c:
                c.execute(
                    "UPDATE harvest_runs SET finished_at=?, status=?, total_stored=?, results=? WHERE id=?",
                    (finished, status, total_stored, json.dumps(results, default=str), run_id),
                )
        except Exception as exc:
            logger.error("harvest history: could not record end of run %s: %s", run_id, exc)

    def close_stale(self, older_than_minutes: int = 10) -> int:
        """Rows still 'running' after a restart belong to a process that no longer exists."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=older_than_minutes)).isoformat()
        now = datetime.now(UTC).isoformat()
        try:
            if self._sb:
                res = self._sb.table("table_harvest_runs").update(
                    {"status": "interrupted", "finished_at": now}
                ).eq("status", "running").lt("started_at", cutoff).execute()
                return len(res.data or [])
            with self._sqlite() as c:
                return c.execute(
                    "UPDATE harvest_runs SET status='interrupted', finished_at=? WHERE status='running' AND started_at < ?",
                    (now, cutoff),
                ).rowcount
        except Exception as exc:
            logger.warning("harvest history: close_stale failed: %s", exc)
            return 0

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        if self._sb:
            rows = self._sb.table("table_harvest_runs").select("*").order("started_at", desc=True).limit(limit).execute().data
            return list(rows or [])
        with self._sqlite() as c:
            out = []
            for r in c.execute("SELECT * FROM harvest_runs ORDER BY id DESC LIMIT ?", (limit,)):
                d = dict(r)
                for k in ("sectors", "results"):
                    try:
                        d[k] = json.loads(d.get(k) or "null")
                    except ValueError:
                        pass
                out.append(d)
            return out
