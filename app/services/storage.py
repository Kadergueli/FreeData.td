from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


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
        """Persist a source response in table_raw when Supabase is active."""
        if not self._supabase:
            return None
        response = self._supabase.table("table_raw").insert(
            {
                "secteur": sector,
                "source_api": source,
                "donnee_brute": records,
                "statut": "brut",
                "nb_lignes": len(records),
                "notes_agent": "Recorded automatically by FreeDatatd before normalization.",
            }
        ).execute()
        return response.data[0]["id"]

    def upsert_many(self, observations: Iterable[ObservationCreate], raw_record_id: int | None = None) -> int:
        return self._upsert_many(observations, raw_record_id)

    def store_validation_report(self, raw_record_id: int | None, received: int, accepted: int, rejected: int, errors: list[str]) -> None:
        """Complete the raw-to-published audit trail in table_rapports."""
        if not self._supabase or raw_record_id is None:
            return
        completeness = accepted / received if received else 0.0
        self._supabase.table("table_rapports").insert(
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
        ).execute()

    def save_study(self, sector: str | None, model: str, observations_used: int, report: str) -> int | None:
        """Keep generated LLM studies separate from the verified source data."""
        if self._supabase:
            try:
                response = self._supabase.table("table_etudes").insert(
                    {
                        "secteur": sector,
                        "modele": model,
                        "nb_observations": observations_used,
                        "rapport": report,
                        "statut": "generated",
                    }
                ).execute()
                return response.data[0]["id"]
            except Exception as exc:
                logger.warning("Supabase table_etudes insert failed (non-fatal): %s", exc)
                return None
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO studies (sector, model, observations_used, report) VALUES (?, ?, ?, ?)",
                (sector, model, observations_used, report),
            )
        return cursor.lastrowid

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
        """Write clean records then publish them using a single batch per table."""
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
            clean_response = self._supabase.table("table_clean").insert(clean_payloads).execute()
        except Exception as exc:
            logger.error("Supabase table_clean batch insert failed: %s", exc)
            raise RuntimeError(f"Storage error writing to table_clean: {exc}") from exc

        clean_ids = [item["id"] for item in clean_response.data]

        # Batch insert audit logs (one entry per clean record, non-critical)
        log_payloads = [
            {
                "id_donnee": clean_id,
                "agent": "Agent 2",
                "type_operation": "ds_clean",
                "valeur_avant": "Raw source payload retained in table_raw.",
                "valeur_apres": f"{row['indicator']}={row['value']} {row['unit']}",
                "regle_appliquee": ("ds_flag" if row.get("flags") else "canonical")[:10],
                "superviseur": "FreeDatatd",
            }
            for clean_id, row in zip(clean_ids, rows)
        ]
        try:
            self._supabase.table("table_logs").insert(log_payloads).execute()
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
            self._supabase.table("table_public").upsert(
                public_payloads,
                on_conflict="secteur,source_api,date_reference,indicateur,region",
            ).execute()
        except Exception:
            # Fallback to insert if the unique index table_public_dedup_idx is not yet created on Supabase
            try:
                self._supabase.table("table_public").insert(public_payloads).execute()
            except Exception as exc:
                logger.error("Supabase table_public batch insert failed: %s", exc)
                raise RuntimeError(f"Storage error writing to table_public: {exc}") from exc

        return len(rows)

    def list_observations(self, sector: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if self._supabase:
            query = self._supabase.table("table_public").select("*")
            if sector:
                query = query.eq("secteur", sector)
            query = query.order("date_reference", desc=True).limit(limit)
            return [self._public_to_observation(row) for row in query.execute().data]
        query = "SELECT * FROM observations"
        parameters: list[Any] = []
        if sector:
            query += " WHERE sector = ?"
            parameters.append(sector)
        query += " ORDER BY reference_date DESC LIMIT ?"
        parameters.append(limit)
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(query, parameters).fetchall()]

    @staticmethod
    def _public_to_observation(row: dict[str, Any]) -> dict[str, Any]:
        """Keep one English API contract while Supabase retains French field names."""
        return {
            "id": row["id"], "sector": row["secteur"], "indicator": row["indicateur"],
            "value": row["valeur"], "unit": row["unite"], "reference_date": row["date_reference"],
            "country_code": row["pays"], "region": row["region"], "source": row["source_api"],
            "source_url": None, "license": row["licence"], "notes": row["notes_publiques"],
            "collected_at": row["date_publication"],
        }

    def catalog(self) -> list[dict[str, Any]]:
        if self._supabase:
            # Query distinct catalog entries by sector to ensure all sectors are represented
            rows = []
            for sec in ["agriculture", "environment", "markets", "transport", "education", "economy"]:
                res = self._supabase.table("table_public").select("secteur,indicateur,source_api,date_reference").eq("secteur", sec).order("date_reference", desc=True).limit(1000).execute()
                if res.data:
                    for item in res.data:
                        rows.append({"sector": item["secteur"], "indicator": item["indicateur"], "source": item["source_api"], "reference_date": item["date_reference"]})
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
            try:
                raw_res = self._supabase.table("table_raw").select("id, secteur, source_api, nb_lignes, date_collecte, donnee_brute").order("id", desc=True).limit(1).execute()
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

                clean_res = self._supabase.table("table_clean").select("id, secteur, source_api, indicateur, valeur, unite, region, statut_qualite, regles_appliquees, instructions_texte").order("id", desc=True).limit(1).execute()
                if clean_res.data:
                    audit["clean_sample"] = clean_res.data[0]

                logs_res = self._supabase.table("table_logs").select("id, agent, type_operation, valeur_apres, regle_appliquee, timestamp").order("id", desc=True).limit(8).execute()
                audit["logs"] = logs_res.data or []

                reports_res = self._supabase.table("table_rapports").select("score_global, score_completude, score_coherence, nb_anomalies, statut_final").order("id", desc=True).limit(1).execute()
                if reports_res.data:
                    rep = reports_res.data[0]
                    audit["reports_summary"].update(rep)

                audit["reports_summary"]["total_raw"] = self._supabase.table("table_raw").select("id", count="exact").limit(1).execute().count or 0
                audit["reports_summary"]["total_clean"] = self._supabase.table("table_clean").select("id", count="exact").limit(1).execute().count or 0
                audit["reports_summary"]["total_public"] = self._supabase.table("table_public").select("id", count="exact").limit(1).execute().count or 0
            except Exception as exc:
                logger.warning("Failed to retrieve Supabase pipeline audit: %s", exc)

        return audit


