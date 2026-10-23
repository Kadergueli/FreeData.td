"""Persistence for the admin area: who may administer, and an audit trail of what they did.

Supabase when configured (table_admins, table_admin_audit — see supabase/admin_setup.sql),
SQLite otherwise (development)."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.services.storage import ObservationRepository, _with_retry

logger = logging.getLogger(__name__)

ROLES = ("owner", "admin")


class AdminStore:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    # ── SQLite (development) ──────────────────────────────────────────────
    def _sqlite(self):
        connection = self.repository._connection()
        connection.execute(
            """CREATE TABLE IF NOT EXISTS admins (
                email TEXT PRIMARY KEY, role TEXT NOT NULL DEFAULT 'admin',
                added_by TEXT, created_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                admin_email TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT)"""
        )
        return connection

    @property
    def _sb(self):
        return self.repository._supabase

    # ── Admins ────────────────────────────────────────────────────────────
    def get_role(self, email: str) -> str | None:
        email = email.strip().lower()
        try:
            if self._sb:
                rows = _with_retry(
                    lambda: self._sb.table("table_admins").select("role").eq("email", email).limit(1).execute(),
                    attempts=2, label="admin get_role",
                ).data
                return rows[0]["role"] if rows else None
            with self._sqlite() as c:
                row = c.execute("SELECT role FROM admins WHERE email = ?", (email,)).fetchone()
                return row["role"] if row else None
        except Exception as exc:
            logger.warning("admin get_role failed: %s", exc)
            return None

    def list_admins(self) -> list[dict[str, Any]]:
        if self._sb:
            rows = self._sb.table("table_admins").select("email,role,added_by,created_at").order("created_at").execute().data
            return list(rows or [])
        with self._sqlite() as c:
            return [dict(r) for r in c.execute("SELECT email, role, added_by, created_at FROM admins ORDER BY created_at")]

    def add_admin(self, email: str, role: str, added_by: str) -> None:
        email = email.strip().lower()
        if role not in ROLES:
            raise ValueError("role must be 'owner' or 'admin'")
        if self._sb:
            self._sb.table("table_admins").upsert(
                {"email": email, "role": role, "added_by": added_by}, on_conflict="email"
            ).execute()
            return
        with self._sqlite() as c:
            c.execute(
                "INSERT INTO admins (email, role, added_by, created_at) VALUES (?,?,?,?) "
                "ON CONFLICT(email) DO UPDATE SET role=excluded.role",
                (email, role, added_by, datetime.now(UTC).isoformat()),
            )

    def remove_admin(self, email: str) -> bool:
        email = email.strip().lower()
        if self._sb:
            res = self._sb.table("table_admins").delete().eq("email", email).execute()
            return bool(res.data)
        with self._sqlite() as c:
            return c.execute("DELETE FROM admins WHERE email = ?", (email,)).rowcount > 0

    # ── Audit trail ───────────────────────────────────────────────────────
    def log(self, admin_email: str, action: str, target: str | None = None, detail: dict | None = None) -> None:
        """Best-effort by design: an audit failure must be loud in the logs but must not
        turn a completed admin action into an error for the user."""
        try:
            if self._sb:
                self._sb.table("table_admin_audit").insert(
                    {"admin_email": admin_email, "action": action, "target": target, "detail": detail or {}}
                ).execute()
                return
            with self._sqlite() as c:
                c.execute(
                    "INSERT INTO admin_audit (created_at, admin_email, action, target, detail) VALUES (?,?,?,?,?)",
                    (datetime.now(UTC).isoformat(), admin_email, action, target, json.dumps(detail or {}, default=str)),
                )
        except Exception as exc:
            logger.error("ADMIN AUDIT WRITE FAILED (%s by %s on %s): %s", action, admin_email, target, exc)

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._sb:
            rows = self._sb.table("table_admin_audit").select("*").order("created_at", desc=True).limit(limit).execute().data
            return list(rows or [])
        with self._sqlite() as c:
            out = []
            for r in c.execute("SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)):
                d = dict(r)
                try:
                    d["detail"] = json.loads(d.get("detail") or "{}")
                except ValueError:
                    pass
                out.append(d)
            return out
