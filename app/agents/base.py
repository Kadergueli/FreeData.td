from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
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


# Licence and attribution that must travel with the rows of a source whose terms differ from the
# platform default (CC BY 4.0). Matched on the `source` text of a record.
SOURCE_TERMS: dict[str, tuple[str, str]] = {
    "OpenStreetMap": ("ODbL 1.0", "© OpenStreetMap contributors (openstreetmap.org/copyright)."),
    "IMF": ("IMF terms of use", "Source: International Monetary Fund, World Economic Outlook (DataMapper)."),
    "OurAirports": ("Public domain", "Source: OurAirports (ourairports.com), public-domain data."),
    "WFP": ("CC BY-IGO 3.0", "Source: World Food Programme (WFP), via the Humanitarian Data Exchange."),
}


def source_failure_line(name: str, exc: BaseException, known: list[str]) -> str | None:
    """"name: reason" for a source that raised, unless `known` already carries that reason (the
    collectors that explain themselves put the same sentence in the list before raising)."""
    reason = str(exc)
    return None if any(reason and reason in line for line in known) else f"{name}: {reason}"


def source_terms(source: str, agent_name: str) -> tuple[str, str]:
    """(licence, notes) for a record: the source's own terms when known, else the default."""
    for key, (licence, attribution) in SOURCE_TERMS.items():
        if str(source).startswith(key):
            return licence, attribution
    return "CC BY 4.0", f"Automated harvest by {agent_name} from {source}."


def wb_years(first_year: int) -> str:
    """World Bank `date` parameter from first_year up to the current year ("2015:2026")."""
    return f"{first_year}:{datetime.now(UTC).year}"


def recent_window(months: int = 12, lag_days: int = 7) -> tuple[str, str]:
    """(start, end) ISO dates covering the last `months` months, ending `lag_days` ago.

    Archive APIs (Open-Meteo) publish with a few days of delay, so asking for "today" returns
    nulls. The window moves forward with the calendar: a frozen year would silently stop
    collecting new data.
    """
    end = datetime.now(UTC).date() - timedelta(days=lag_days)
    year, month = end.year, end.month - months
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1).isoformat(), end.isoformat()


def nasa_power_years(span: int = 5) -> tuple[str, str]:
    """(start, end) years for NASA POWER monthly data: the last `span` years up to this one."""
    year = datetime.now(UTC).year
    return str(year - span + 1), str(year)



def _retry_after_seconds(value: str | None, default: float) -> float:
    """Parse a Retry-After header value (seconds or HTTP-date) into a float."""
    if not value:
        return default

    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_date = parsedate_to_datetime(value)
        if retry_date.tzinfo is None:
            return default
        delay = (retry_date - datetime.now(retry_date.tzinfo)).total_seconds()
        return max(0.0, delay)
    except (TypeError, ValueError, OverflowError):
        return default

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
        # One line per source that failed during collect(): a run can succeed overall (other
        # sources answered) while one source is down, and that must not stay invisible.
        self.source_errors: list[str] = []

    def note_source_failure(self, name: str, exc: Exception) -> None:
        """Record a failed source for the run result, unless its message was already recorded by
        the collector itself (the same text twice only adds noise)."""
        message = str(exc)
        if not any(message in existing for existing in self.source_errors):
            self.source_errors.append(f"{name}: {message}")

    @staticmethod
    async def fetch_json_with_retry(
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        throttle_seconds: float = 0.15,
        errors: list[str] | None = None,
    ) -> Any:
        """GET a JSON document, retrying transient failures. Returns None when it still fails;
        the reason of the last failure (HTTP status, timeout...) is appended to `errors` so the
        caller can report WHY, not just that it failed."""
        req_headers = {"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedatatd.onrender.com)"}
        if headers:
            req_headers.update(headers)

        if throttle_seconds > 0:
            await asyncio.sleep(throttle_seconds)

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url, params=params, headers=req_headers)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = _retry_after_seconds(retry_after, default=float(2 ** attempt))
                    if errors is not None:
                        errors[:] = ["HTTP 429 (rate limited)"]
                    logger.warning("HTTP 429 Rate limited on %s. Backing off for %.1fs (attempt %d/%d)", url, wait_time, attempt, max_retries)
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if errors is not None:
                    errors[:] = [f"HTTP {exc.response.status_code}: {exc.response.text[:120]!r}"]
                if exc.response.status_code >= 500 and attempt < max_retries:
                    wait_time = float(2 ** attempt)
                    logger.warning("HTTP %d Server Error on %s. Retrying in %.1fs...", exc.response.status_code, url, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning("HTTP status error fetching %s: %s", url, exc)
                    return None
            except (httpx.RequestError, json.JSONDecodeError, ValueError, TypeError) as exc:
                if errors is not None:
                    errors[:] = [f"{type(exc).__name__}: {str(exc)[:150] or 'no detail'}"]
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
        req_headers = {"User-Agent": "FreeData.td Open Data Engine/1.0 (+https://freedatatd.onrender.com)"}
        if headers:
            req_headers.update(headers)

        if throttle_seconds > 0:
            await asyncio.sleep(throttle_seconds)

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url, params=params, headers=req_headers)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = _retry_after_seconds(retry_after, default=float(2 ** attempt))
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
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
            if math.isfinite(obs.value):
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
            is_percent_unit = "%" in obs.unit or "percent" in obs.unit.lower()

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
            elif "humidity" in ind.lower() or "percentage" in ind.lower() or ("rate" in ind.lower() and is_percent_unit):
                # 0-100 only binds quantities expressed in percent. A mortality rate "per 1,000
                # live births" legitimately exceeds 100 (Chad: ~105), and inflation may be negative.
                if (val < 0.0 or val > 100.0) and not is_valid_neg:
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
        observation.country_code = observation.country_code.strip().upper()
        if observation.reference_date.year < 1960:
            errors.append("reference_date is outside the supported range (<1960)")
        if observation.country_code != "TCD":
            errors.append("only Chad (TCD) is currently supported")
        return errors

    async def run(self, source: str = "demo") -> CollectionResult:
        started_at = datetime.now(UTC)
        self.source_errors = []
        raw_records = await self.collect(source)
        # Storage calls are synchronous (Supabase client, sqlite3, time.sleep in the retry
        # helper). Run in a worker thread so a collection never freezes the API for everyone.
        await asyncio.to_thread(self._archive_raw, source, raw_records, started_at)
        raw_record_id = await asyncio.to_thread(self.repository.store_raw_batch, self.sector, source, raw_records)

        normalized_list: list[ObservationCreate] = []
        errors: list[str] = [f"source failed: {msg}" for msg in self.source_errors]

        if not raw_records:
            # A source answering with nothing is a silent failure (frozen date window, API moved,
            # network blocked): surface it in the run result and the logs instead of "0 stored, OK".
            logger.warning("%s/%s: the source returned no records.", self.sector, source)
            errors.append("no data received from the source (check the source or its date window)")

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

        report: dict[str, Any] = {}
        stored = await asyncio.to_thread(self.repository.upsert_many, accepted, raw_record_id=raw_record_id, report=report)
        await asyncio.to_thread(
            self.repository.store_validation_report,
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
            held=int(report.get("held", 0)),
            started_at=started_at,
            completed_at=datetime.now(UTC),
            errors=errors,
        )

    RAW_ARCHIVE_KEEP = 40  # newest files kept per sector; the full raw payload also lives in table_raw

    def _prune_raw_archive(self, raw_directory: Path) -> None:
        """Without a cap, every collection leaves a JSON file on the server's (small) disk."""
        files = sorted(raw_directory.glob(f"{self.sector}_*.json"), key=lambda f: f.stat().st_mtime)
        for old in files[:-self.RAW_ARCHIVE_KEEP]:
            try:
                old.unlink()
            except OSError as exc:
                logger.warning("Could not remove old raw archive %s: %s", old, exc)

    def _archive_raw(self, source: str, records: list[dict[str, Any]], collected_at: datetime) -> None:
        try:
            raw_directory = PROJECT_ROOT / "data" / "raw"
            raw_directory.mkdir(parents=True, exist_ok=True)
            filename = f"{self.sector}_{source}_{collected_at.strftime('%Y%m%dT%H%M%S')}.json"
            (raw_directory / filename).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            self._prune_raw_archive(raw_directory)
        except Exception as exc:
            # Best-effort local archival copy - never block a collection run over
            # this, but a silent `pass` here means a real problem (disk full,
            # permissions) leaves zero trace anywhere. Log it instead.
            logger.warning("Failed to archive raw records for %s/%s: %s", self.sector, source, exc)
