from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from app.agents import (
    AgricultureAgent,
    EconomyAgent,
    EducationAgent,
    EnvironmentAgent,
    MarketsAgent,
    TransportAgent,
)
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
        # Do not run immediate heavy harvest on server startup to keep API 100% responsive
        self.next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
        try:
            await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            return

        while self.is_running:
            await self.run_harvest_job()
            self.next_run = datetime.now(UTC) + timedelta(seconds=self.interval_seconds)
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def run_harvest_job(self) -> dict[str, Any]:
        logger.info("Starting scheduled autonomous data harvest across active sector agents...")
        self.last_run = datetime.now(UTC)
        total_stored = 0
        agent_results = {}

        agents = [
            ("agriculture", AgricultureAgent(self.repository)),
            ("environment", EnvironmentAgent(self.repository)),
            ("markets", MarketsAgent(self.repository)),
            ("economy", EconomyAgent(self.repository)),
            ("transport", TransportAgent(self.repository)),
            ("education", EducationAgent(self.repository)),
        ]

        for sec_name, agent in agents:
            try:
                res = await agent.run(source="all")
                agent_results[sec_name] = res.model_dump(mode="json")
                total_stored += res.stored
            except Exception as exc:
                logger.error("Error harvesting %s: %s", sec_name, exc)
                agent_results[sec_name] = {"error": str(exc)}

        self.last_result = {
            "timestamp": self.last_run.isoformat(),
            "total_stored": total_stored,
            "sectors": agent_results,
        }
        logger.info("Scheduled harvest completed: %d total records stored.", total_stored)
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
