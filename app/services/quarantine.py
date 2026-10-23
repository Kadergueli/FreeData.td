"""Quarantine: observations the pipeline cannot vouch for are held back until a human decides.

A row flagged SUPERVISOR_REVIEW (impossible or out-of-domain value) used to be published
with a flag nobody looked at. Now it waits here; an administrator approves it as is,
corrects the value, or rejects it. Only then does it reach the public table.

Supabase when configured (table_quarantine — see supabase/quarantine_setup.sql),
SQLite otherwise (development)."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.services.storage import ObservationRepository, _with_retry

logger = logging.getLogger(__name__)

HOLD_FLAG = "SUPERVISOR_REVIEW"
STATUSES = ("pending", "approved", "corrected", "rejected")
KEY_COLS = ("secteur", "source_api", "date_reference", "indicateur", "region")


def to_record(row: dict[str, Any], raw_record_id: int | None) -> dict[str, Any]:
    """Serialised observation (storage._serialise) -> quarantine record."""
    return {
        "secteur": row["sector"],
        "source_api": str(row["source"])[:30],
        "date_reference": str(row["reference_date"]),
        "indicateur": row["indicator"],
        "valeur": float(row["value"]),
        "unite": str(row["unit"])[:30],
        "region": row["region"],
        "pays": str(row["country_code"])[:3],
        "licence": row.get("license"),
        "source_url": row.get("source_url"),
        "notes": row.get("notes"),
        "flags": sorted(set(row.get("flags") or [])),
        "id_raw": raw_record_id,
    }


def _same(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def _key(rec: dict[str, Any]) -> tuple:
    return tuple(str(rec[c]) for c in KEY_COLS)


class QuarantineStore:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @property
    def _sb(self):
        return self.repository._supabase

    def _sqlite(self):
        c = self.repository._connection()
        c.execute(
            """CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                secteur TEXT NOT NULL, source_api TEXT NOT NULL, date_reference TEXT NOT NULL,
                indicateur TEXT NOT NULL, valeur REAL NOT NULL, unite TEXT, region TEXT NOT NULL,
                pays TEXT NOT NULL DEFAULT 'TCD', licence TEXT, source_url TEXT, notes TEXT,
                flags TEXT NOT NULL DEFAULT '[]', id_raw INTEGER, status TEXT NOT NULL DEFAULT 'pending',
                corrected_value REAL, reviewed_by TEXT, reviewed_at TEXT, review_note TEXT)"""
        )
        c.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS quarantine_pending_key ON quarantine
               (secteur, source_api, date_reference, indicateur, region) WHERE status = 'pending'"""
        )
        return c

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        d = dict(row)
        if isinstance(d.get("flags"), str):
            try:
                d["flags"] = json.loads(d["flags"])
            except ValueError:
                d["flags"] = []
        d["flags"] = d.get("flags") or []
        return d

    # ── holding ──────────────────────────────────────────────────────────
    def _existing(self, sectors: set[str]) -> dict[tuple, list[dict[str, Any]]]:
        found: dict[tuple, list[dict[str, Any]]] = {}
        for sector in sorted(sectors):
            if self._sb:
                start = 0
                while True:
                    page = _with_retry(
                        lambda sector=sector, start=start: self._sb.table("table_quarantine").select("*")
                        .eq("secteur", sector).range(start, start + 999).execute(),
                        attempts=2, label="quarantine existing",
                    ).data or []
                    for item in page:
                        found.setdefault(_key(item), []).append(item)
                    if len(page) < 1000:
                        break
                    start += 1000
            else:
                with self._sqlite() as c:
                    for item in c.execute("SELECT * FROM quarantine WHERE secteur = ?", (sector,)):
                        found.setdefault(_key(dict(item)), []).append(dict(item))
        return found

    def hold(self, rows: list[dict[str, Any]], raw_record_id: int | None) -> int:
        """Keep these rows out of the public data. A row already waiting is refreshed, not
        duplicated; one an administrator already ruled on, with the very same value, is not
        brought back (they would be asked the same question every day). Raises on failure:
        rows that are neither published nor held would silently vanish."""
        records = [to_record(r, raw_record_id) for r in rows]
        if not records:
            return 0
        existing = self._existing({r["secteur"] for r in records})
        now = datetime.now(UTC).isoformat()
        seen: set[tuple] = set()
        for rec in records:
            k = _key(rec)
            if k in seen:
                continue
            seen.add(k)
            entries = existing.get(k, [])
            pending = next((e for e in entries if e["status"] == "pending"), None)
            if pending:
                if _same(pending["valeur"], rec["valeur"]):
                    continue
                self._update_pending(pending["id"], rec, now)
            elif any(_same(e["valeur"], rec["valeur"]) for e in entries):
                continue
            else:
                self._insert(rec, now)
        return len(seen)

    def _insert(self, rec: dict[str, Any], now: str) -> None:
        if self._sb:
            _with_retry(lambda: self._sb.table("table_quarantine").insert(rec).execute(),
                        attempts=2, label="quarantine insert")
            return
        with self._sqlite() as c:
            c.execute(
                """INSERT INTO quarantine (created_at, updated_at, secteur, source_api, date_reference, indicateur,
                   valeur, unite, region, pays, licence, source_url, notes, flags, id_raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (now, now, rec["secteur"], rec["source_api"], rec["date_reference"], rec["indicateur"], rec["valeur"],
                 rec["unite"], rec["region"], rec["pays"], rec["licence"], rec["source_url"], rec["notes"],
                 json.dumps(rec["flags"]), rec["id_raw"]),
            )

    def _update_pending(self, qid: int, rec: dict[str, Any], now: str) -> None:
        fields = {k: rec[k] for k in ("valeur", "notes", "flags", "id_raw")}
        if self._sb:
            _with_retry(lambda: self._sb.table("table_quarantine").update(dict(fields, updated_at=now))
                        .eq("id", qid).eq("status", "pending").execute(), attempts=2, label="quarantine refresh")
            return
        with self._sqlite() as c:
            c.execute("UPDATE quarantine SET valeur=?, notes=?, flags=?, id_raw=?, updated_at=? WHERE id=? AND status='pending'",
                      (fields["valeur"], fields["notes"], json.dumps(fields["flags"]), fields["id_raw"], now, qid))

    # ── review ───────────────────────────────────────────────────────────
    def list(self, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
        if status != "all" and status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        if self._sb:
            q = self._sb.table("table_quarantine").select("*")
            if status != "all":
                q = q.eq("status", status)
            rows = q.order("created_at", desc=True).limit(limit).execute().data or []
            return [self._decode(r) for r in rows]
        with self._sqlite() as c:
            if status == "all":
                cur = c.execute("SELECT * FROM quarantine ORDER BY id DESC LIMIT ?", (limit,))
            else:
                cur = c.execute("SELECT * FROM quarantine WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
            return [self._decode(dict(r)) for r in cur]

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(STATUSES, 0)
        if self._sb:
            for st in STATUSES:
                res = self._sb.table("table_quarantine").select("id", count="exact").eq("status", st).limit(1).execute()
                out[st] = int(res.count or 0)
            return out
        with self._sqlite() as c:
            for st, n in c.execute("SELECT status, COUNT(*) FROM quarantine GROUP BY status"):
                out[st] = n
        return out

    def get(self, qid: int) -> dict[str, Any] | None:
        if self._sb:
            rows = self._sb.table("table_quarantine").select("*").eq("id", qid).limit(1).execute().data
            return self._decode(rows[0]) if rows else None
        with self._sqlite() as c:
            row = c.execute("SELECT * FROM quarantine WHERE id = ?", (qid,)).fetchone()
            return self._decode(dict(row)) if row else None

    def decide(self, qid: int, status: str, admin: str, note: str | None = None, corrected: float | None = None) -> bool:
        """pending -> approved/corrected/rejected, atomically. False if someone decided first."""
        assert status in ("approved", "corrected", "rejected")
        now = datetime.now(UTC).isoformat()
        if self._sb:
            res = self._sb.table("table_quarantine").update({
                "status": status, "reviewed_by": admin, "reviewed_at": now, "review_note": note,
                "corrected_value": corrected, "updated_at": now,
            }).eq("id", qid).eq("status", "pending").execute()
            return bool(res.data)
        with self._sqlite() as c:
            return c.execute(
                "UPDATE quarantine SET status=?, reviewed_by=?, reviewed_at=?, review_note=?, corrected_value=?, updated_at=? "
                "WHERE id=? AND status='pending'", (status, admin, now, note, corrected, now, qid)).rowcount > 0

    def reopen(self, qid: int) -> None:
        """Undo a decision whose publication failed, so the row is not left 'approved' but unpublished."""
        now = datetime.now(UTC).isoformat()
        try:
            if self._sb:
                self._sb.table("table_quarantine").update({
                    "status": "pending", "reviewed_by": None, "reviewed_at": None, "review_note": None,
                    "corrected_value": None, "updated_at": now}).eq("id", qid).execute()
                return
            with self._sqlite() as c:
                c.execute("UPDATE quarantine SET status='pending', reviewed_by=NULL, reviewed_at=NULL, review_note=NULL, "
                          "corrected_value=NULL, updated_at=? WHERE id=?", (now, qid))
        except Exception as exc:
            logger.error("quarantine row %s left decided but unpublished: %s", qid, exc)
