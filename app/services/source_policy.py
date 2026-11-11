"""What the admin decides about each data source: status, where its data may be used, call limits.

The *licence* facts (what the official page says, when it was read) live in the register
(app/licences_register.json) and are read-only here. The *policy* (is the source switched on,
may its rows go to the paid layer, what quota do we respect) is the admin's decision and is stored:
Supabase `table_source_policy` (supabase/source_policy_setup.sql) or SQLite in development."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.licences import commercial_safe, load_register
from app.services.sources import SECTOR_SOURCES
from app.services.storage import ObservationRepository, _with_retry

logger = logging.getLogger(__name__)

STATUSES = ("active", "paused", "planned", "retired")
LAYERS = ("open", "both")          # open = free public layer only; both = may also feed a paid offer
LIMIT_FIELDS = ("limit_minute", "limit_hour", "limit_day", "limit_month")

# Quotas published by the providers, used until the admin sets their own.
DEFAULT_LIMITS: dict[str, dict[str, int]] = {
    "open-meteo": {"limit_minute": 600, "limit_hour": 5000, "limit_day": 10000, "limit_month": 300000},
    "open-meteo-transport": {"limit_minute": 600, "limit_hour": 5000, "limit_day": 10000, "limit_month": 300000},
}

# Sources that give the same kind of data: the admin picks which one feeds the platform.
ALTERNATIVES: list[dict[str, Any]] = [
    {"domain": "weather", "sources": ["open-meteo", "nasa-power", "copernicus-era5"],
     "note": "Weather and climate series for the regions of Chad."},
]

# Row source name (table_public.source_api) -> register id, longest prefix wins.
_ROW_ALIASES = {
    "world bank pink sheet": "pink-sheet", "world bank": "world-bank", "imf": "imf", "open-meteo": "open-meteo",
    "nasa power": "nasa-power", "nasa firms": "nasa-firms", "unhcr": "unhcr", "unesco": "unesco-uis",
    "unicef": "unicef", "openstreetmap": "open-street-map", "who": "who-gho", "dhs": "dhs", "fews": "fews-net",
    "wfp": "wfp", "faostat": "faostat", "ourairports": "ourairports", "inseed": "inseed",
    "copernicus": "copernicus-era5",
}


def row_source_id(source: str, sector: str | None = None) -> str | None:
    s = (source or "").lower()
    hit = max((a for a in _ROW_ALIASES if s.startswith(a)), key=len, default=None)
    if hit is None:
        return None
    sid = _ROW_ALIASES[hit]
    if sid == "open-meteo" and sector == "transport":
        return "open-meteo-transport"
    if sid == "nasa-power" and sector == "agriculture":
        return "nasa-power-agro"
    return sid


def default_policy(entry: dict[str, Any]) -> dict[str, Any]:
    collectable = any(entry["id"] in ids for ids in SECTOR_SOURCES.values())
    pol: dict[str, Any] = {
        "status": "active" if collectable else "planned",
        "layer": "both" if commercial_safe(entry) else "open",
        "notes": None, "updated_by": None, "updated_at": None, "customised": False,
    }
    pol.update({f: None for f in LIMIT_FIELDS})
    pol.update(DEFAULT_LIMITS.get(entry["id"], {}))
    return pol


def policy_warnings(entry: dict[str, Any], pol: dict[str, Any]) -> list[str]:
    """Codes the screen translates: what does not add up between the licence and the decision."""
    out = []
    if pol["layer"] == "both" and not commercial_safe(entry):
        out.append("commercial_not_cleared")
    if pol["status"] == "active" and not entry.get("verified_on"):
        out.append("active_unverified")
    return out


class SourcePolicyStore:
    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @property
    def _sb(self):
        return self.repository._supabase

    def _sqlite(self):
        c = self.repository._connection()
        c.execute(
            """CREATE TABLE IF NOT EXISTS source_policy (
                source_id TEXT PRIMARY KEY, status TEXT NOT NULL, layer TEXT NOT NULL,
                limit_minute INTEGER, limit_hour INTEGER, limit_day INTEGER, limit_month INTEGER,
                notes TEXT, updated_by TEXT, updated_at TEXT)"""
        )
        return c

    def stored(self) -> dict[str, dict[str, Any]]:
        if self._sb:
            rows = _with_retry(lambda: self._sb.table("table_source_policy").select("*").execute(),
                               attempts=2, label="source_policy list").data
        else:
            with self._sqlite() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM source_policy")]
        return {r["source_id"]: r for r in (rows or [])}

    def save(self, source_id: str, values: dict[str, Any], admin: str) -> None:
        row = {"source_id": source_id, **values, "updated_by": admin, "updated_at": datetime.now(UTC).isoformat()}
        if self._sb:
            self._sb.table("table_source_policy").upsert(row, on_conflict="source_id").execute()
            return
        cols = list(row)
        with self._sqlite() as c:
            c.execute(
                f"INSERT INTO source_policy ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                f"ON CONFLICT(source_id) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in cols if k != 'source_id')}",
                [row[k] for k in cols],
            )

    def merged(self) -> list[dict[str, Any]]:
        stored = self.stored()
        out = []
        for entry in load_register():
            pol = default_policy(entry)
            if entry["id"] in stored:
                s = stored[entry["id"]]
                pol.update({k: s.get(k) for k in ("status", "layer", "notes", "updated_by", "updated_at", *LIMIT_FIELDS)})
                pol["customised"] = True
            out.append({**entry, "commercial_safe": commercial_safe(entry), "policy": pol,
                        "warnings": policy_warnings(entry, pol)})
        return out
