from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from app.agents.agriculture import AgricultureAgent
from app.services.storage import ObservationRepository

logger = logging.getLogger(__name__)


class AutonomousHarvesterScheduler:
    """Background service that periodically collects open API data into Supabase/SQLite."""

    def __init__(self, interval_hours: int = 6) -> None:
        self.interval_seconds = interval_hours * 3600
        self._task: asyncio.Task | None = None
        self.is_running = False
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.last_result: dict[str, Any] | None = None
        self.repository = ObservationRepository()

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
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
        # Initial run on startup after 5 seconds delay
        await asyncio.sleep(5)
        while self.is_running:
            await self.run_harvest_job()
            self.next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def run_harvest_job(self) -> dict[str, Any]:
        logger.info("Starting scheduled autonomous data harvest...")
        self.last_run = datetime.now(UTC)
        try:
            agent = AgricultureAgent(self.repository)
            result = await agent.run(source="all")
            self.last_result = result.model_dump(mode="json")
            logger.info("Scheduled harvest completed: %d records stored.", result.stored)
            return self.last_result
        except Exception as exc:
            logger.error("Error during scheduled harvest: %s", exc)
            self.last_result = {"error": str(exc), "timestamp": self.last_run.isoformat()}
            return self.last_result

    def get_status(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "interval_hours": self.interval_seconds // 3600,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_result": self.last_result,
        }


scheduler_service = AutonomousHarvesterScheduler(interval_hours=24)
