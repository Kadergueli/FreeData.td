from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Any

import asyncio
import httpx
import logging

from app.config import PROJECT_ROOT
from app.schemas import CollectionResult, ObservationCreate
from app.services.storage import ObservationRepository

logger = logging.getLogger(__name__)

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
    sector: str
    name: str

    def __init__(self, repository: ObservationRepository) -> None:
        self.repository = repository

    @staticmethod
    async def fetch_json_with_retry(
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        throttle_seconds: float = 0.15,
    ) -> Any:
        req_headers = {"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedata.td)"}
        if headers:
            req_headers.update(headers)

        if throttle_seconds > 0:
            await asyncio.sleep(throttle_seconds)

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url, params=params, headers=req_headers)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after and retry_after.isdigit() else float(2 ** attempt)
                    logger.warning("HTTP 429 Rate limited on %s. Backing off for %.1fs (attempt %d/%d)", url, wait_time, attempt, max_retries)
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < max_retries:
                    wait_time = float(2 ** attempt)
                    logger.warning("HTTP %d Server Error on %s. Retrying in %.1fs...", exc.response.status_code, url, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning("HTTP status error fetching %s: %s", url, exc)
                    return None
            except (httpx.RequestError, json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Network or format error fetching %s (attempt %d/%d): %s", url, attempt, max_retries, exc)
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                else:
                    return None
        return None

    @staticmethod
    async def fetch_text_with_retry(
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        throttle_seconds: float = 0.15,
    ) -> str | None:
        req_headers = {"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedata.td)"}
        if headers:
            req_headers.update(headers)

        if throttle_seconds > 0:
            await asyncio.sleep(throttle_seconds)

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url, params=params, headers=req_headers)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after and retry_after.isdigit() else float(2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.text
            except Exception as exc:
                logger.warning("HTTP error fetching text from %s: %s", url, exc)
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                else:
                    return None
        return None

    @abstractmethod
    async def collect(self, source: str) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        pass

    def process_data_science_rules(self, observations: list[ObservationCreate]) -> list[ObservationCreate]:
        if not observations:
            return observations

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
                iqr_bounds[ind] = (q1 - 3 * iqr, q3 + 3 * iqr)

        processed: list[ObservationCreate] = []

        for obs in observations:
            flags: list[str] = list(obs.flags or [])
            val = obs.value
            ind = obs.indicator.strip()

            strictly_positive = (
                "rainfall", "precip", "yield", "area", "price", "production",
                "population", "distance", "fertilizer", "accident"
            )
            valid_negative = ("temp", "temperature", "growth", "growth rate", "inflation", "balance", "variation")

            is_strictly_positive = any(k in ind.lower() for k in strictly_positive)
            is_valid_neg = any(k in ind.lower() for k in valid_negative)

            if val < 0:
                if "rainfall" in ind.lower() or "precip" in ind.lower():
                    val = 0.0
                    flags.append("NEGATIVE_ERROR")
                elif is_strictly_positive and not is_valid_neg:
                    flags.extend(["NEGATIVE_ERROR", "SUPERVISOR_REVIEW"])

            if "brightness" in ind.lower() or obs.unit.upper() == "K":
                if val < 200.0 or val > 600.0:
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])
            elif "temp" in ind.lower():
                if val < -5.0 or val > 55.0:
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])
            elif "humidity" in ind.lower() or "rate" in ind.lower() or "percentage" in ind.lower():
                if (val < 0.0 or val > 100.0) and "growth" not in ind.lower():
                    flags.extend(["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"])

            if ind in iqr_bounds:
                low_bound, high_bound = iqr_bounds[ind]
                if val < low_bound or val > high_bound:
                    if "OUTLIER" not in flags:
                        flags.append("OUTLIER")

            obs.value = val
            obs.flags = sorted(list(set(flags)))
            processed.append(obs)

        return processed

    def validate(self, observation: ObservationCreate) -> list[str]:
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
        try:
            raw_directory = PROJECT_ROOT / "data" / "raw"
            raw_directory.mkdir(parents=True, exist_ok=True)
            filename = f"{self.sector}_{source}_{collected_at.strftime('%Y%m%dT%H%M%S')}.json"
            (raw_directory / filename).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
