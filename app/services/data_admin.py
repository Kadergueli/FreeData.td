"""Administrator tools for already-published data: find, correct, delete (archived), restore.

Supabase when configured (table_public + table_deleted_observations — see
supabase/data_admin_setup.sql), SQLite otherwise (development).

A correction or a deletion is only durable if the next harvest does not undo it, so each one
also records the *source's* value as 'rejected' in the quarantine table: a harvest that brings
back that same value is dropped; a harvest that brings a different (revised) value publishes."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.schemas import ObservationCreate
from app.services.quarantine import QuarantineStore
from app.services.storage import ObservationRepository, _clean_search_term, _with_retry, invalidate_cache

logger = logging.getLogger(__name__)


class DataAdminStore:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository
        self.quarantine = QuarantineStore(repository)

    @property
    def _sb(self):
        return self.repository._supabase

    def _sqlite(self):
        c = self.repository._connection()
        c.execute(
            """CREATE TABLE IF NOT EXISTS deleted_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, deleted_at TEXT NOT NULL, deleted_by TEXT NOT NULL,
                reason TEXT NOT NULL, row TEXT NOT NULL, restored_at TEXT, restored_by TEXT)"""
        )
        return c

    # ── normalisation ─────────────────────────────────────────────────────
    @staticmethod
    def _from_public(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": r["id"], "sector": r.get("secteur"), "indicator": r.get("indicateur"), "value": r.get("valeur"),
            "unit": r.get("unite"), "reference_date": str(r.get("date_reference")), "region": r.get("region"),
            "source": r.get("source_api"), "country_code": r.get("pays") or "TCD", "license": r.get("licence"),
            "notes": r.get("notes_publiques"), "approved_by": r.get("approuve_par"),
        }

    @staticmethod
    def _from_sqlite(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": r["id"], "sector": r["sector"], "indicator": r["indicator"], "value": r["value"], "unit": r["unit"],
            "reference_date": str(r["reference_date"]), "region": r["region"], "source": r["source"],
            "country_code": r.get("country_code") or "TCD", "license": r.get("license"), "notes": r.get("notes"),
            "approved_by": None,
        }

    @staticmethod
    def _as_record(o: dict[str, Any], value: float) -> dict[str, Any]:
        """Quarantine-table record for this observation (used to remember a value to suppress)."""
        return {
            "secteur": o["sector"], "source_api": str(o["source"])[:30], "date_reference": o["reference_date"],
            "indicateur": o["indicator"], "valeur": float(value), "unite": str(o.get("unit") or "")[:30],
            "region": o["region"], "pays": str(o.get("country_code") or "TCD")[:3], "licence": o.get("license"),
            "source_url": None, "notes": None, "flags": ["ADMIN_OVERRIDE"], "id_raw": None,
        }

    # ── read ──────────────────────────────────────────────────────────────
    def search(self, sector: str | None = None, q: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = _clean_search_term(q)
        if self._sb:
            query = self._sb.table("table_public").select("*")
            if sector:
                query = query.eq("secteur", sector)
            if q:
                query = query.or_(f"indicateur.ilike.*{q}*,source_api.ilike.*{q}*,region.ilike.*{q}*")
            rows = query.order("date_reference", desc=True).limit(limit).execute().data or []
            return [self._from_public(r) for r in rows]
        sql, params = "SELECT * FROM observations", []
        cond = []
        if sector:
            cond.append("sector = ?"); params.append(sector)
        if q:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            cond.append("(indicator LIKE ? ESCAPE '\\' OR source LIKE ? ESCAPE '\\' OR region LIKE ? ESCAPE '\\')")
            params += [like, like, like]
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        with self.repository._connection() as c:
            return [self._from_sqlite(dict(r)) for r in c.execute(sql + " ORDER BY reference_date DESC, id DESC LIMIT ?", (*params, limit))]

    def get(self, oid: int) -> dict[str, Any] | None:
        if self._sb:
            rows = self._sb.table("table_public").select("*").eq("id", oid).limit(1).execute().data
            return self._from_public(rows[0]) if rows else None
        with self.repository._connection() as c:
            row = c.execute("SELECT * FROM observations WHERE id = ?", (oid,)).fetchone()
            return self._from_sqlite(dict(row)) if row else None

    # ── write ─────────────────────────────────────────────────────────────
    def correct(self, oid: int, value: float, admin: str, reason: str) -> dict[str, Any] | None:
        """Replace a published value. Returns the observation as it was, or None if it is gone."""
        before = self.get(oid)
        if before is None:
            return None
        # remember the source's value first: if this fails nothing was changed
        self.quarantine.suppress(self._as_record(before, before["value"]), admin, f"corrected: {reason}")
        note = f"[Valeur corrigée par un administrateur : {before['value']:g} -> {value:g}. Motif : {reason}]"
        notes = " ".join(x for x in (before.get("notes"), note) if x)
        if self._sb:
            _with_retry(lambda: self._sb.table("table_public").update(
                {"valeur": value, "notes_publiques": notes, "approuve_par": admin}).eq("id", oid).execute(),
                attempts=2, label="admin correct")
        else:
            with self.repository._connection() as c:
                c.execute("UPDATE observations SET value = ?, notes = ? WHERE id = ?", (value, notes, oid))
        invalidate_cache()
        return before

    def delete(self, oid: int, admin: str, reason: str) -> dict[str, Any] | None:
        """Remove a published value. It is archived first (restorable) and its source value is
        remembered so the next harvest does not silently bring it back."""
        row = self.get(oid)
        if row is None:
            return None
        now = datetime.now(UTC).isoformat()
        if self._sb:
            _with_retry(lambda: self._sb.table("table_deleted_observations").insert(
                {"deleted_by": admin, "reason": reason, "row": row}).execute(), attempts=2, label="admin archive")
        else:
            with self._sqlite() as c:
                c.execute("INSERT INTO deleted_observations (deleted_at, deleted_by, reason, row) VALUES (?,?,?,?)",
                          (now, admin, reason, json.dumps(row, default=str)))
        self.quarantine.suppress(self._as_record(row, row["value"]), admin, f"deleted: {reason}")
        if self._sb:
            _with_retry(lambda: self._sb.table("table_public").delete().eq("id", oid).execute(), attempts=2, label="admin delete")
        else:
            with self.repository._connection() as c:
                c.execute("DELETE FROM observations WHERE id = ?", (oid,))
        invalidate_cache()
        return row

    def list_deleted(self, limit: int = 50) -> list[dict[str, Any]]:
        if self._sb:
            rows = self._sb.table("table_deleted_observations").select("*").is_("restored_at", "null") \
                .order("deleted_at", desc=True).limit(limit).execute().data or []
            return list(rows)
        with self._sqlite() as c:
            out = []
            for r in c.execute("SELECT * FROM deleted_observations WHERE restored_at IS NULL ORDER BY id DESC LIMIT ?", (limit,)):
                d = dict(r)
                d["row"] = json.loads(d["row"])
                out.append(d)
            return out

    def _get_deleted(self, aid: int) -> dict[str, Any] | None:
        if self._sb:
            rows = self._sb.table("table_deleted_observations").select("*").eq("id", aid).limit(1).execute().data
            return rows[0] if rows else None
        with self._sqlite() as c:
            r = c.execute("SELECT * FROM deleted_observations WHERE id = ?", (aid,)).fetchone()
            if not r:
                return None
            d = dict(r)
            d["row"] = json.loads(d["row"])
            return d

    def restore(self, aid: int, admin: str) -> dict[str, Any] | None:
        """Put an archived observation back. None if unknown or already restored."""
        entry = self._get_deleted(aid)
        if entry is None or entry.get("restored_at"):
            return None
        r = entry["row"]
        obs = ObservationCreate(
            sector=r["sector"], indicator=r["indicator"], value=r["value"], unit=r.get("unit") or "unit",
            reference_date=r["reference_date"], country_code=r.get("country_code") or "TCD", region=r["region"],
            source=r["source"], license=r.get("license") or "CC BY 4.0",
            notes=" ".join(x for x in (r.get("notes"), "[Restaurée par un administrateur]") if x), flags=["REVIEWED"],
        )
        self.repository._upsert_many([obs], None, hold_for_review=False, approved_by=admin)
        now = datetime.now(UTC).isoformat()
        if self._sb:
            self._sb.table("table_deleted_observations").update({"restored_at": now, "restored_by": admin}).eq("id", aid).execute()
        else:
            with self._sqlite() as c:
                c.execute("UPDATE deleted_observations SET restored_at=?, restored_by=? WHERE id=?", (now, admin, aid))
        invalidate_cache()
        return r
