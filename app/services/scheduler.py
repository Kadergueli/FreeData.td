from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from app.agents import (
    AgricultureAgent,
    DemographyAgent,
    EconomyAgent,
    EducationAgent,
    EnergyAgent,
    EnvironmentAgent,
    HealthAgent,
    MarketsAgent,
    TransportAgent,
)
from app.services.cadence import split_due
from app.services.harvest_runs import HarvestRunStore, summarize_results
from app.services.storage import SECTOR_IDS, ObservationRepository

logger = logging.getLogger(__name__)

# Safety net: one sector that never answers must not keep the whole harvest "running" for ever
# (and block every later run). The slowest legitimate sector (FEWS NET prices) takes ~2 minutes.
SECTOR_TIMEOUT_SECONDS = 20 * 60


class AutonomousHarvesterScheduler:
    """Background service that periodically collects open API data into Supabase/SQLite."""

    def __init__(self, interval_hours: int = 6) -> None:
        self.interval_seconds = interval_hours * 3600
        self._task: asyncio.Task | None = None
        self._bg_task: asyncio.Task | None = None  # on-demand run started via the API
        self._job_lock = asyncio.Lock()
        self._job_running = False
        self.is_running = False
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.last_result: dict[str, Any] | None = None
        self.repository = ObservationRepository()
        self.history = HarvestRunStore(self.repository)
        # Set by the caller for the run about to start (read once inside the job lock).
        self._next_sectors: list[str] | None = None
        self._next_skipped: dict[str, str] = {}
        self.current_run: dict[str, Any] | None = None

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        # A run still marked 'running' belongs to the process that just died.
        self.history.close_stale()
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Autonomous Harvester Scheduler started (interval: %ds).", self.interval_seconds)

    def stop(self) -> None:
        if not self.is_running:
            return
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Autonomous Harvester Scheduler stopped.")

    async def _scheduler_loop(self) -> None:
        # Do not run immediate heavy harvest on server startup to keep API 100% responsive
        self.next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
        try:
            await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            return

        while self.is_running:
            await self.run_harvest_job(trigger="scheduler", only_due=True)
            self.next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    @staticmethod
    def _validate_sectors(sectors: list[str] | None) -> None:
        unknown = [x for x in (sectors or []) if x not in SECTOR_IDS]
        if unknown:
            raise ValueError(f"unknown sector(s): {', '.join(unknown)}")

    def start_background_job(
        self, sectors: list[str] | None = None, trigger: str = "api", triggered_by: str | None = None,
        only_due: bool = False,
    ) -> bool:
        """Start a harvest (all sectors, or the given ones) without waiting for it (an HTTP
        request would time out long before 8 sectors finish). Returns False when one is
        already running."""
        self._validate_sectors(sectors)
        if self._job_running or (self._bg_task is not None and not self._bg_task.done()):
            return False
        self._bg_task = asyncio.create_task(self.run_harvest_job(sectors, trigger, triggered_by, only_due))
        return True

    async def run_harvest_job(
        self, sectors: list[str] | None = None, trigger: str = "api", triggered_by: str | None = None,
        only_due: bool = False,
    ) -> dict[str, Any]:
        """Public entry-point — skips if a job is already in progress.

        With only_due, the sectors whose collection rhythm (app/services/cadence.py) says
        they were collected recently are left out; automatic runs use it, administrators
        do not."""
        self._validate_sectors(sectors)
        if self._job_running:
            logger.warning("Harvest job skipped because another job is already running.")
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "total_stored": 0,
                "status": "skipped",
                "reason": "another harvest job is already running",
                "sectors": {},
            }

        async with self._job_lock:
            if self._job_running:
                logger.warning("Harvest job skipped because another job is already running.")
                return {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "total_stored": 0,
                    "status": "skipped",
                    "reason": "another harvest job is already running",
                    "sectors": {},
                }

            self._job_running = True
            self._next_sectors = list(sectors) if sectors else None
            self._next_skipped = {}
            if only_due:
                candidates = self._next_sectors if self._next_sectors is not None else list(SECTOR_IDS)
                self._next_sectors, self._next_skipped = await self._due_sectors(candidates)
            planned = self._next_sectors if self._next_sectors is not None else list(SECTOR_IDS)
            run_id: int | None = None
            result: dict[str, Any] | None = None
            try:
                run_id = await asyncio.to_thread(self.history.start, trigger, planned, triggered_by)
                # no e-mail here: this dict is part of the public /scheduler-status payload
                self.current_run = {"id": run_id, "trigger": trigger, "sectors": planned,
                                    "started_at": datetime.now(UTC).isoformat()}
                result = await self._run_harvest_job()
                return result
            finally:
                self._job_running = False
                self.current_run = None
                if result is None:  # the job itself crashed or was cancelled
                    await asyncio.shield(asyncio.to_thread(self.history.finish, run_id, "failed", 0, {}))
                else:
                    status, summary = summarize_results(result.get("sectors") or {})
                    await asyncio.shield(asyncio.to_thread(
                        self.history.finish, run_id, status, int(result.get("total_stored") or 0), summary))

    async def _due_sectors(self, candidates: list[str]) -> tuple[list[str], dict[str, str]]:
        """Split the candidates into due / skipped using the durable run history. If the
        history cannot be read, everything is due: collecting too much beats collecting nothing."""
        try:
            runs = await asyncio.to_thread(self.history.list_runs, 120)
        except Exception as exc:
            logger.warning("collection rhythm: history unreadable (%s) — every sector is treated as due.", exc)
            return list(candidates), {}
        return split_due(runs, candidates)

    async def _run_harvest_job(self) -> dict[str, Any]:
        logger.info("Starting scheduled autonomous data harvest across active sector agents...")
        self.last_run = datetime.now(UTC)
        total_stored = 0
        agent_results = {}

        agents = [
            ("agriculture", AgricultureAgent(self.repository)),
            ("environment", EnvironmentAgent(self.repository)),
            ("markets", MarketsAgent(self.repository)),
            ("economy", EconomyAgent(self.repository)),
            ("health", HealthAgent(self.repository)),
            ("energy", EnergyAgent(self.repository)),
            ("transport", TransportAgent(self.repository)),
            ("education", EducationAgent(self.repository)),
            ("demography", DemographyAgent(self.repository)),
        ]

        wanted = self._next_sectors
        for sec_name, agent in agents:
            if wanted is not None and sec_name not in wanted:
                continue
            try:
                res = await asyncio.wait_for(agent.run(source="all"), timeout=SECTOR_TIMEOUT_SECONDS)
                agent_results[sec_name] = res.model_dump(mode="json")
                total_stored += res.stored
            except asyncio.TimeoutError:
                logger.error("Harvest of %s stopped: no end after %d s.", sec_name, SECTOR_TIMEOUT_SECONDS)
                agent_results[sec_name] = {"error": f"stopped after {SECTOR_TIMEOUT_SECONDS // 60} minutes without finishing"}
            except Exception as exc:
                logger.error("Error harvesting %s: %s", sec_name, exc)
                agent_results[sec_name] = {"error": str(exc)}

        # Housekeeping: the audit trail grows with every stored row; keep only the recent part.
        await asyncio.to_thread(self.repository.purge_old_logs)

        self.last_result = {
            "timestamp": self.last_run.isoformat(),
            "total_stored": total_stored,
            "status": "completed",
            "sectors": agent_results,
            "skipped": dict(self._next_skipped),
        }
        logger.info("Scheduled harvest completed: %d total records stored.", total_stored)
        return self.last_result

    def get_public_status(self) -> dict[str, Any]:
        """Status safe for unauthenticated visitors: counts and ok/failed flags only. Raw error
        messages (library errors, URLs, internals) stay in the logs and the admin area."""
        last = self.last_result or {}
        sectors: dict[str, dict[str, Any]] = {}
        for name, res in (last.get("sectors") or {}).items():
            if not isinstance(res, dict) or res.get("error"):
                sectors[name] = {"error": True}
            else:
                sectors[name] = {"stored": res.get("stored")}
        return {
            "is_running": self.is_running,
            "job_running": self._job_running,
            "interval_hours": self.interval_seconds // 3600,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_result": {
                "timestamp": last.get("timestamp"),
                "total_stored": last.get("total_stored"),
                "status": last.get("status"),
                "sectors": sectors,
                "skipped": sorted((last.get("skipped") or {}).keys()),
            } if last else None,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "job_running": self._job_running,
            "interval_hours": self.interval_seconds // 3600,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_result": self.last_result,
            "current_run": self.current_run,
        }


scheduler_service = AutonomousHarvesterScheduler(interval_hours=24)
