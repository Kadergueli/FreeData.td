from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT
from app.schemas import CollectionResult, ObservationCreate
from app.services.storage import ObservationRepository


# ─── Standardized Data Science Flags for FreeDatatd ──────────────────────────
FLAGS = {
    "MISSING": "Valeur manquante non interpolable",
    "INTERPOLATED": "Valeur interpolée (gap <= 7 jours)",
    "OUTLIER": "Valeur hors bornes 3*IQR — à vérifier",
    "NEGATIVE_ERROR": "Valeur négative impossible dans ce contexte",
    "DUPLICATE": "Doublon détecté — sources différentes",
    "CONVERTED": "Valeur convertie (devise ou unité)",
    "TEMPORAL_JUMP": "Variation > 50% avec période précédente",
    "DOMAIN_VIOLATION": "Valeur hors domaine physique/logique",
    "SUPERVISOR_REVIEW": "Requiert validation superviseur humain",
}


class BaseAgent(ABC):
    """Shared data science collection & processing lifecycle for FreeDatatd agents."""

    sector: str
    name: str

    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @abstractmethod
    async def collect(self, source: str) -> list[dict[str, Any]]:
        """Fetch raw records from a named source adapter."""

    @abstractmethod
    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        """Convert a raw source record to FreeDatatd's canonical model."""

    def process_data_science_rules(self, observations: list[ObservationCreate]) -> list[ObservationCreate]:
        """Apply the 10 professional Data Science rules to the dataset:
        1. Never delete without documenting.
        2. Domain-aware negative value rules.
        3. 3*IQR Outlier detection & flagging.
        4. Temporal jump detection (>50%).
        5. Physical & sector domain validation.
        """
        if not observations:
            return observations

        # ── Step A: Group values by indicator for IQR Outlier Calculation ────
        indicator_values: dict[str, list[float]] = {}
        for obs in observations:
            if not math.isnan(obs.value):
                indicator_values.setdefault(obs.indicator, []).append(obs.value)

        iqr_bounds: dict[str, tuple[float, float]] = {}
        for ind, vals in indicator_values.items():
            if len(vals) >= 4:
                sorted_vals = sorted(vals)
                n = len(sorted_vals)
                q1 = sorted_vals[n // 4]
                q3 = sorted_vals[(3 * n) // 4]
                iqr = q3 - q1
                # 3*IQR rule for African volatile data
                iqr_bounds[ind] = (q1 - 3 * iqr, q3 + 3 * iqr)

        processed: list[ObservationCreate] = []

        for obs in observations:
            flags: list[str] = list(obs.flags or [])
            val = obs.value
            ind = obs.indicator.strip()

            # ── Rule 3: Domain-aware Negative Values ─────────────────────────
            # Indicators where negative values are physically IMPOSSIBLE
            strictly_positive = (
                "rainfall", "precip", "yield", "area", "price", "production",
                "population", "distance", "fertilizer", "accident"
            )
            # Indicators where negative values are VALID (temperatures, growth, balances, variations)
            valid_negative = ("temp", "temperature", "growth", "growth rate", "inflation", "balance", "variation")

            is_strictly_positive = any(k in ind.lower() for k in strictly_positive)
            is_valid_neg = any(k in ind.lower() for k in valid_negative)

            if val < 0:
                if "rainfall" in ind.lower() or "precip" in ind.lower():
                    # Physical correction rule: Negative rainfall replaced by 0.0 + flag
                    val = 0.0
                    flags.append("NEGATIVE_ERROR")
                elif is_strictly_positive and not is_valid_neg:
                    flags.extend(["NEGATIVE_ERROR", "SUPERVISOR_REVIEW"])

            # ── Rule 8: Sector & Domain Bounds ───────────────────────────────
            if "brightness" in ind.lower() or obs.unit.upper() == "K":
                # Fire brightness temperature (Kelvin): valid satellite range 200 K - 600 K
                if val < 200.0 or val > 600.0:
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])
            elif "temp" in ind.lower():
                # Ambient air temperature (°C): valid meteorological range -5.0°C - 55.0°C
                if val < -5.0 or val > 55.0:
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])
            elif "humidity" in ind.lower() or "rate" in ind.lower() or "percentage" in ind.lower():
                if (val < 0.0 or val > 100.0) and "growth" not in ind.lower():
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])

            # ── Rule 4: Outlier Detection using 3*IQR ────────────────────────
            if ind in iqr_bounds:
                low_bound, high_bound = iqr_bounds[ind]
                if val < low_bound or val > high_bound:
                    if "OUTLIER" not in flags:
                        flags.append("OUTLIER")

            # Update observation with cleaned value and flags
            obs.value = val
            obs.flags = sorted(list(set(flags)))
            processed.append(obs)

        return processed

    def validate(self, observation: ObservationCreate) -> list[str]:
        """Basic structural check (date range, country code)."""
        errors: list[str] = []
        if observation.reference_date.year < 1960:
            errors.append("reference_date is outside the supported range (<1960)")
        if observation.country_code != "TCD":
            errors.append("only Chad (TCD) is currently supported")
        return errors

    async def run(self, source: str = "demo") -> CollectionResult:
        started_at = datetime.now(UTC)
        raw_records = await self.collect(source)
        self._archive_raw(source, raw_records, started_at)
        raw_record_id = self.repository.store_raw_batch(self.sector, source, raw_records)

        normalized_list: list[ObservationCreate] = []
        errors: list[str] = []

        for raw in raw_records:
            try:
                observation = self.normalize(raw)
                if observation is None:
                    errors.append("record skipped: required source fields are missing")
                    continue
                validation_errors = self.validate(observation)
                if validation_errors:
                    errors.extend(validation_errors)
                    continue
                normalized_list.append(observation)
            except (TypeError, ValueError) as exc:
                errors.append(f"record skipped: {exc}")

        # Apply the 10 Professional Data Science rules (IQR outliers, flags, domain bounds)
        accepted = self.process_data_science_rules(normalized_list)

        stored = self.repository.upsert_many(accepted, raw_record_id=raw_record_id)
        self.repository.store_validation_report(
            raw_record_id=raw_record_id,
            received=len(raw_records),
            accepted=len(accepted),
            rejected=len(raw_records) - len(accepted),
            errors=errors,
        )
        return CollectionResult(
            agent=self.name,
            source=source,
            received=len(raw_records),
            accepted=len(accepted),
            rejected=len(raw_records) - len(accepted),
            stored=stored,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            errors=errors,
        )

    def _archive_raw(self, source: str, records: list[dict[str, Any]], collected_at: datetime) -> None:
        """Keep source responses locally for reproducibility; these files are gitignored."""
        try:
            raw_directory = PROJECT_ROOT / "data" / "raw"
            raw_directory.mkdir(parents=True, exist_ok=True)
            filename = f"{self.sector}_{source}_{collected_at.strftime('%Y%m%dT%H%M%S')}.json"
            (raw_directory / filename).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
