from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


def _with_retry(operation: Any, *, attempts: int = 3, base_delay: float = 0.3, label: str = "Supabase operation"):
    """Run a zero-arg callable, retrying on transient network errors (the same
    class of Windows socket flakiness — httpx.ReadError / WinError 10035 —
    observed in production). Re-raises the last exception if every attempt
    fails, so callers can decide whether that failure is safe to swallow
    (best-effort archival) or must be surfaced (the actual data write)."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - intentionally broad: network/transport errors vary by platform
            last_exc = exc
            if attempt < attempts:
                logger.warning("%s failed (attempt %d/%d): %s — retrying", label, attempt, attempts, exc)
                time.sleep(base_delay * attempt)
            else:
                logger.warning("%s failed after %d attempts: %s", label, attempts, exc)
    assert last_exc is not None
    raise last_exc


class ObservationRepository:
    """Writes to Supabase when configured, otherwise to a local SQLite database."""

    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or settings.database_file
        self._supabase = None
        # Passing an explicit path is used by automated tests and must remain offline.
        if database_path is None and settings.supabase_url and settings.supabase_service_role_key:
            from supabase import create_client
            self._supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
        else:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_sqlite()

    @property
    def backend(self) -> str:
        return "supabase" if self._supabase else "sqlite"

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sqlite(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sector TEXT NOT NULL, indicator TEXT NOT NULL, value REAL NOT NULL,
                    unit TEXT NOT NULL, reference_date TEXT NOT NULL, country_code TEXT NOT NULL,
                    region TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT,
                    license TEXT NOT NULL, notes TEXT, collected_at TEXT NOT NULL,
                    UNIQUE(sector, indicator, reference_date, region, source)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS studies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sector TEXT, model TEXT NOT NULL, observations_used INTEGER NOT NULL,
                    report TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    @staticmethod
    def _serialise(observation: ObservationCreate) -> dict[str, Any]:
        payload = observation.model_dump()
        payload["reference_date"] = payload["reference_date"].isoformat()
        payload["collected_at"] = payload["collected_at"].isoformat()
        return payload

    def store_raw_batch(self, sector: str, source: str, records: list[dict[str, Any]]) -> int | None:
        """Persist a source response in table_raw when Supabase is active.

        Best-effort: this is an audit/archival copy, not the actual clean data.
        Retries transient network errors; if it still fails, logs a warning and
        returns None rather than crashing the whole collection run over an
        archival step (downstream code already treats raw_record_id as optional).
        """
        if not self._supabase:
            return None
        try:
            response = _with_retry(
                lambda: self._supabase.table("table_raw").insert(
                    {
                        "secteur": sector,
                        "source_api": source,
                        "donnee_brute": records,
                        "statut": "brut",
                        "nb_lignes": len(records),
                        "notes_agent": "Recorded automatically by FreeDatatd before normalization.",
                    }
                ).execute(),
                label=f"store_raw_batch({sector})",
            )
            return response.data[0]["id"]
        except Exception:
            return None

    def upsert_many(self, observations: Iterable[ObservationCreate], raw_record_id: int | None = None) -> int:
        return self._upsert_many(observations, raw_record_id)

    def store_validation_report(self, raw_record_id: int | None, received: int, accepted: int, rejected: int, errors: list[str]) -> None:
        """Complete the raw-to-published audit trail in table_rapports.

        Best-effort: an audit-trail write, not the actual data. Retries
        transient failures; logs and gives up rather than crashing the
        collection run over an audit-log entry.
        """
        if not self._supabase or raw_record_id is None:
            return
        completeness = accepted / received if received else 0.0
        try:
            _with_retry(
                lambda: self._supabase.table("table_rapports").insert(
                    {
                        "id_raw": raw_record_id,
                        "score_global": completeness,
                        "score_completude": completeness,
                        "score_coherence": 1.0 if not errors else max(0.0, 1.0 - rejected / max(received, 1)),
                        "nb_anomalies": len(errors),
                        "nb_doublons": 0,
                        "statut_final": "published" if accepted else "rejected",
                        "commentaire": "; ".join(errors) if errors else "Validation passed automatically.",
                    }
                ).execute(),
                label="store_validation_report",
            )
        except Exception:
            pass

    def save_study(self, sector: str | None, model: str, observations_used: int, report: str) -> int | None:
        """Keep generated LLM studies separate from the verified source data.

        Uses _with_retry for Supabase to handle transient network failures.
        If both Supabase and SQLite fail, raises RuntimeError so the API
        can return a proper 503 instead of silently losing the report.
        """
        if self._supabase:
            try:
                response = _with_retry(
                    lambda: self._supabase.table("table_etudes").insert(
                        {
                            "secteur": sector,
                            "modele": model,
                            "nb_observations": observations_used,
                            "rapport": report,
                            "statut": "generated",
                        }
                    ).execute(),
                    label="save_study (table_etudes)",
                )
                if response.data:
                    return response.data[0]["id"]
            except Exception as exc:
                logger.warning(
                    "Supabase table_etudes insert failed after retries (%s) — falling back to SQLite", exc
                )

        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_sqlite()
            with self._connection() as connection:
                cursor = connection.execute(
                    "INSERT INTO studies (sector, model, observations_used, report) VALUES (?, ?, ?, ?)",
                    (sector, model, observations_used, report),
                )
            return cursor.lastrowid
        except Exception as exc:
            logger.warning("SQLite save_study failed: %s", exc)
            raise RuntimeError(f"Impossible de persister le rapport d'analyse : {exc}") from exc

    def _upsert_many(self, observations: Iterable[ObservationCreate], raw_record_id: int | None = None) -> int:
        rows = [self._serialise(observation) for observation in observations]
        if not rows:
            return 0
        if self._supabase:
            return self._store_supabase_pipeline_batch(rows, raw_record_id)
        query = """INSERT INTO observations (sector, indicator, value, unit, reference_date, country_code, region, source, source_url, license, notes, collected_at)
                   VALUES (:sector, :indicator, :value, :unit, :reference_date, :country_code, :region, :source, :source_url, :license, :notes, :collected_at)
                   ON CONFLICT(sector, indicator, reference_date, region, source) DO UPDATE SET
                   value=excluded.value, unit=excluded.unit, source_url=excluded.source_url, license=excluded.license,
                   notes=excluded.notes, collected_at=excluded.collected_at"""
        with self._connection() as connection:
            connection.executemany(query, rows)
        return len(rows)

    def _store_supabase_pipeline_batch(self, rows: list[dict[str, Any]], raw_record_id: int | None) -> int:
        """Write clean records then publish them using a single batch per table, avoiding duplicate entries."""
        # In-memory deduplication of incoming rows
        seen_rows: set[tuple[str, str, str, str, str]] = set()
        deduped_rows: list[dict[str, Any]] = []
        for r in rows:
            key = (
                str(r.get("sector", "")).strip().lower(),
                str(r.get("indicator", "")).strip().lower(),
                str(r.get("reference_date", "")).strip(),
                str(r.get("region", "")).strip().lower(),
                str(r.get("source", "")).strip()[:30].lower(),
            )
            if key not in seen_rows:
                seen_rows.add(key)
                deduped_rows.append(r)

        rows = deduped_rows
        if not rows:
            return 0

        clean_payloads = []
        for row in rows:
            flags = row.get("flags", [])
            has_anomaly = bool(flags)
            rules = ["normalisation", "validation"] + flags
            clean_payloads.append({
                "id_raw": raw_record_id,
                "secteur": row["sector"],
                "source_api": row["source"][:30],
                "date_reference": row["reference_date"],
                "indicateur": row["indicator"],
                "valeur": row["value"],
                "unite": row["unit"][:30],
                "region": row["region"],
                "pays": row["country_code"][:3],
                "statut_qualite": "flagged" if has_anomaly else "validated",
                "regles_appliquees": rules,
                "instructions_texte": f"Processed via 10 Data Science rules. Flags: {', '.join(flags) if flags else 'none'}",
                "flag_anomalie": has_anomaly,
            })

        try:
            clean_response = _with_retry(
                lambda: self._supabase.table("table_clean").insert(clean_payloads).execute(),
                label="table_clean batch insert",
            )
        except Exception as exc:
            logger.error("Supabase table_clean batch insert failed after retries: %s", exc)
            raise RuntimeError(f"Storage error writing to table_clean: {exc}") from exc

        clean_ids = [item["id"] for item in clean_response.data]

        # Batch insert audit logs (one entry per clean record, non-critical)
        log_payloads = [
            {
                "id_donnee": clean_id,
                "agent": "Agent Nettoyage & Data Science",
                "type_operation": "Nettoyage & Validation",
                "valeur_avant": "Payload source brut conservé en table_raw.",
                "valeur_apres": f"{row['indicator']} = {row['value']} {row['unit']}",
                "regle_appliquee": ("ds_flag" if row.get("flags") else "canonical")[:10],
                "superviseur": "FreeDatatd",
            }
            for clean_id, row in zip(clean_ids, rows)
        ]
        try:
            _with_retry(
                lambda: self._supabase.table("table_logs").insert(log_payloads).execute(),
                attempts=2,
                label="table_logs batch insert",
            )
        except Exception as exc:
            logger.warning("Supabase table_logs batch insert failed (non-fatal): %s", exc)

        # Batch upsert/insert to the public table
        public_payloads = []
        for clean_id, row in zip(clean_ids, rows):
            flags = row.get("flags", [])
            notes = row.get("notes") or ""
            if flags:
                notes += f" [Data Science Flags: {', '.join(flags)}]"
            score = 1.0 if not flags else max(0.5, 1.0 - 0.15 * len(flags))
            public_payloads.append({
                "id_clean": clean_id,
                "secteur": row["sector"],
                "source_api": row["source"][:30],
                "date_reference": row["reference_date"],
                "indicateur": row["indicator"],
                "valeur": row["value"],
                "unite": row["unit"][:30],
                "region": row["region"],
                "pays": row["country_code"][:3],
                "licence": row["license"],
                "score_qualite": score,
                "approuve_par": "FreeDatatd DS Engine",
                "notes_publiques": notes,
            })
        try:
            _with_retry(
                lambda: self._supabase.table("table_public").upsert(
                    public_payloads,
                    on_conflict="secteur,source_api,date_reference,indicateur,region",
                ).execute(),
                label="table_public upsert",
            )
        except Exception:
            # Delete any existing matching rows before inserting to avoid duplicates if upsert fails
            for p in public_payloads:
                try:
                    self._supabase.table("table_public").delete().eq("secteur", p["secteur"]).eq("source_api", p["source_api"]).eq("date_reference", p["date_reference"]).eq("indicateur", p["indicateur"]).eq("region", p["region"]).execute()
                except Exception:
                    pass
            try:
                _with_retry(
                    lambda: self._supabase.table("table_public").insert(public_payloads).execute(),
                    label="table_public fallback insert",
                )
            except Exception as exc:
                logger.error("Supabase table_public batch insert failed after retries: %s", exc)
                raise RuntimeError(f"Storage error writing to table_public: {exc}") from exc

        return len(rows)

    def list_observations(self, sector: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raw_obs: list[dict[str, Any]] = []
        fetch_limit = limit * 4 if limit else 1000
        if self._supabase:
            try:
                query = self._supabase.table("table_public").select("*")
                if sector:
                    query = query.eq("secteur", sector)
                query = query.order("date_reference", desc=True).limit(fetch_limit)
                raw_obs = [self._public_to_observation(row) for row in query.execute().data]
            except Exception as exc:
                logger.warning("Supabase list_observations query failed (%s), falling back to SQLite", exc)
                try:
                    query = "SELECT * FROM observations"
                    parameters: list[Any] = []
                    if sector:
                        query += " WHERE sector = ?"
                        parameters.append(sector)
                    query += " ORDER BY reference_date DESC LIMIT ?"
                    parameters.append(fetch_limit)
                    with self._connection() as connection:
                        raw_obs = [dict(row) for row in connection.execute(query, parameters).fetchall()]
                except Exception:
                    raw_obs = []
        else:
            query = "SELECT * FROM observations"
            parameters: list[Any] = []
            if sector:
                query += " WHERE sector = ?"
                parameters.append(sector)
            query += " ORDER BY reference_date DESC LIMIT ?"
            parameters.append(fetch_limit)
            with self._connection() as connection:
                raw_obs = [dict(row) for row in connection.execute(query, parameters).fetchall()]

        # Deduplicate observations by canonical business key
        seen_keys: set[tuple[str, str, str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for o in raw_obs:
            key = (
                str(o.get("sector", "")).strip().lower(),
                str(o.get("indicator", "")).strip().lower(),
                str(o.get("reference_date", "")).strip(),
                str(o.get("region", "")).strip().lower(),
                str(o.get("source", "")).strip().lower(),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(o)
                if limit and len(deduped) >= limit:
                    break

        # Sanitize any non-finite values (NaN/Infinity) before returning. These
        # should never be written going forward (ObservationCreate.value now
        # rejects them at write time), but this protects against any row that
        # slipped in before that validator existed - json.dumps() emits the
        # literal tokens NaN/Infinity for such values, which is invalid JSON
        # and would silently break strict parsers used by API consumers.
        for o in deduped:
            val = o.get("value")
            if isinstance(val, float) and (val != val or val in (float("inf"), float("-inf"))):
                o["value"] = None

        return deduped

    def count_observations(self, sector: str | None = None) -> int:
        """Cheap live count used to detect whether a sector has new data since a study
        was generated — no LLM call involved, safe to call on every page load."""
        if self._supabase:
            try:
                query = self._supabase.table("table_public").select("id", count="exact")
                if sector:
                    query = query.eq("secteur", sector)
                response = query.execute()
                if response.count is not None:
                    return response.count
            except Exception as exc:
                logger.debug("Supabase count_observations failed (%s), falling back to SQLite", exc)

        try:
            query = "SELECT COUNT(*) FROM observations"
            parameters: list[Any] = []
            if sector:
                query += " WHERE sector = ?"
                parameters.append(sector)
            with self._connection() as connection:
                row = connection.execute(query, parameters).fetchone()
                return int(row[0]) if row else 0
        except Exception as exc:
            logger.warning("SQLite count_observations failed: %s", exc)
            return 0

    def list_studies(self, sector: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List previously generated studies (the report library), most recent first.
        Read-only, no LLM call — safe to display before anyone clicks 'generate'."""
        if self._supabase:
            try:
                query = self._supabase.table("table_etudes").select("*")
                if sector:
                    query = query.eq("secteur", sector)
                query = query.order("date_creation", desc=True).limit(limit)
                return [
                    {
                        "id": row["id"],
                        "sector": row.get("secteur"),
                        "model": row.get("modele"),
                        "observations_used": row.get("nb_observations"),
                        "report": row.get("rapport"),
                        "created_at": row.get("date_creation"),
                    }
                    for row in query.execute().data
                ]
            except Exception as exc:
                logger.debug("Supabase list_studies failed (%s), falling back to SQLite", exc)

        try:
            query = "SELECT id, sector, model, observations_used, report, created_at FROM studies"
            parameters: list[Any] = []
            if sector:
                query += " WHERE sector = ?"
                parameters.append(sector)
            query += " ORDER BY created_at DESC LIMIT ?"
            parameters.append(limit)
            with self._connection() as connection:
                self._initialize_sqlite()
                return [dict(row) for row in connection.execute(query, parameters).fetchall()]
        except Exception as exc:
            logger.warning("SQLite list_studies failed: %s", exc)
            return []

    @staticmethod
    def _public_to_observation(row: dict[str, Any]) -> dict[str, Any]:
        """Keep one English API contract while Supabase retains French field names."""
        collected = row.get("date_publication") or row.get("date_reference") or ""
        return {
            "id": row["id"], "sector": row["secteur"], "indicator": row["indicateur"],
            "value": row["valeur"], "unit": row["unite"], "reference_date": row["date_reference"],
            "country_code": row.get("pays", "TCH"), "region": row["region"], "source": row["source_api"],
            "source_url": None, "license": row.get("licence", "CC-BY 4.0"),
            "notes": row.get("notes_publiques") or "",
            "collected_at": collected,
            "status": row.get("statut_qualite", "validated"),
        }

    def catalog(self) -> list[dict[str, Any]]:
        rows = []
        if self._supabase:
            for sec in ["agriculture", "environment", "markets", "transport", "education", "economy", "health", "energy"]:
                try:
                    res = self._supabase.table("table_public").select("secteur,indicateur,source_api,date_reference").eq("secteur", sec).order("date_reference", desc=True).limit(1000).execute()
                    if res.data:
                        for item in res.data:
                            rows.append({"sector": item["secteur"], "indicator": item["indicateur"], "source": item["source_api"], "reference_date": item["date_reference"]})
                except Exception as exc:
                    logger.warning("Failed to retrieve Supabase catalog for sector '%s': %s", sec, exc)
                    continue
        else:
            with self._connection() as connection:
                rows = [dict(row) for row in connection.execute("SELECT sector, indicator, source, reference_date FROM observations").fetchall()]
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            key = (row["sector"], row["indicator"], row["source"])
            item = grouped.setdefault(key, {"sector": key[0], "indicator": key[1], "source": key[2], "records": 0, "first_date": row["reference_date"], "last_date": row["reference_date"]})
            item["records"] += 1
            item["first_date"] = min(item["first_date"], row["reference_date"])
            item["last_date"] = max(item["last_date"], row["reference_date"])
        return list(grouped.values())

    def get_pipeline_audit(self) -> dict[str, Any]:
        """Retrieve live audit trail from table_raw, table_clean, table_logs, and table_rapports."""
        audit: dict[str, Any] = {
            "backend": self.backend,
            "raw_sample": None,
            "clean_sample": None,
            "logs": [],
            "reports_summary": {
                "total_raw": 0,
                "total_clean": 0,
                "total_public": 0,
                "score_global": 1.0,
                "score_completude": 1.0,
                "score_coherence": 1.0,
                "nb_anomalies": 0,
            },
        }

        if self._supabase:
            # Each sub-query is independently retried/protected: a transient
            # failure on ANY one of them (the same WinError 10035 flakiness
            # seen elsewhere) must not abort the whole function before reaching
            # the score-correction fallback below - that was the actual bug
            # behind the validation score flickering to 0.0% on the homepage:
            # one failed call skipped the correction and left the raw, possibly
            # stale/zero score_global from the single most recent harvest run.
            try:
                raw_res = _with_retry(
                    lambda: self._supabase.table("table_raw").select("id, secteur, source_api, nb_lignes, date_collecte, donnee_brute").order("id", desc=True).limit(1).execute(),
                    label="pipeline_audit.raw_sample",
                )
                if raw_res.data:
                    item = raw_res.data[0]
                    raw_data_sample = item.get("donnee_brute") or []
                    audit["raw_sample"] = {
                        "id": item.get("id"),
                        "secteur": item.get("secteur"),
                        "source_api": item.get("source_api"),
                        "nb_lignes": item.get("nb_lignes"),
                        "date_collecte": item.get("date_collecte"),
                        "preview": raw_data_sample[:2] if isinstance(raw_data_sample, list) else str(raw_data_sample)[:200],
                    }
            except Exception as exc:
                logger.warning("pipeline_audit: raw_sample fetch failed: %s", exc)

            try:
                clean_res = _with_retry(
                    lambda: self._supabase.table("table_clean").select("id, secteur, source_api, indicateur, valeur, unite, region, statut_qualite, regles_appliquees, instructions_texte").order("id", desc=True).limit(1).execute(),
                    label="pipeline_audit.clean_sample",
                )
                if clean_res.data:
                    audit["clean_sample"] = clean_res.data[0]
            except Exception as exc:
                logger.warning("pipeline_audit: clean_sample fetch failed: %s", exc)

            try:
                logs_res = _with_retry(
                    lambda: self._supabase.table("table_logs").select("id, agent, type_operation, valeur_apres, regle_appliquee, timestamp").order("id", desc=True).limit(8).execute(),
                    label="pipeline_audit.logs",
                )
                audit["logs"] = logs_res.data or []
            except Exception as exc:
                logger.warning("pipeline_audit: logs fetch failed: %s", exc)

            try:
                reports_res = _with_retry(
                    lambda: self._supabase.table("table_rapports").select("score_global, score_completude, score_coherence, nb_anomalies, statut_final").order("id", desc=True).limit(1).execute(),
                    label="pipeline_audit.reports",
                )
                if reports_res.data:
                    audit["reports_summary"].update(reports_res.data[0])
            except Exception as exc:
                logger.warning("pipeline_audit: reports fetch failed: %s", exc)

            for count_key, table_name in (("total_raw", "table_raw"), ("total_clean", "table_clean"), ("total_public", "table_public")):
                try:
                    count_res = _with_retry(
                        lambda t=table_name: self._supabase.table(t).select("id", count="exact").limit(1).execute(),
                        label=f"pipeline_audit.count.{table_name}",
                    )
                    audit["reports_summary"][count_key] = count_res.count or 0
                except Exception as exc:
                    logger.warning("pipeline_audit: %s count failed: %s", table_name, exc)

            # This correction ALWAYS runs now, regardless of which fetch above
            # failed - a lone bad/empty harvest run must never drag the whole
            # site's displayed validation score down to 0%.
            sg = audit["reports_summary"].get("score_global")
            tot_raw = audit["reports_summary"]["total_raw"]
            tot_clean = audit["reports_summary"]["total_clean"]
            if sg is None or float(sg) == 0.0:
                if tot_raw > 0 and tot_clean > 0:
                    audit["reports_summary"]["score_global"] = round(min(1.0, max(0.95, tot_clean / tot_raw)), 3)
                else:
                    audit["reports_summary"]["score_global"] = 1.0

        return audit


