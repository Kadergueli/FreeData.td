"""Patch 0026 — storage work must not freeze the event loop; cross-sector failure is a 503."""
import asyncio
import time

from fastapi.testclient import TestClient

from app.agents.base import BaseAgent
from app.main import app
from app.schemas import ObservationCreate


class SlowRepo:
    """Every storage call blocks its thread for 0.3 s, like a slow Supabase round-trip."""

    def store_raw_batch(self, *a, **k):
        time.sleep(0.3)

    def upsert_many(self, observations, raw_record_id=None):
        time.sleep(0.3)
        return len(list(observations))

    def store_validation_report(self, **k):
        time.sleep(0.3)


class OneRowAgent(BaseAgent):
    sector = "agriculture"
    name = "one-row"

    async def collect(self, source):
        return [{"i": 1}]

    def normalize(self, record):
        return ObservationCreate(
            sector="agriculture", indicator="Rendement", value=1.0, unit="t/ha",
            reference_date="2024-01-01", country_code="TCD", region="Lac",
            source="World Bank", source_url="https://example.org", license="CC-BY 4.0", notes="n")

    def _archive_raw(self, *a, **k):
        time.sleep(0.3)


def test_collection_does_not_block_other_requests():
    async def scenario():
        worst = 0.0

        async def ticker():
            nonlocal worst
            last = time.perf_counter()
            while True:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                worst = max(worst, now - last - 0.01)
                last = now

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        result = await OneRowAgent(SlowRepo()).run("x")
        await asyncio.sleep(0.05)  # let the ticker resume so it can record any freeze
        task.cancel()
        return result, worst

    result, worst = asyncio.run(scenario())
    assert result.stored == 1
    # 4 x 0.3 s of blocking work happened; the loop itself must stay responsive.
    assert worst < 0.15, f"event loop froze for {worst:.2f}s"


def test_cross_sector_failure_is_503_not_empty_200(monkeypatch):
    from app import main
    from app.services.storage import invalidate_cache

    invalidate_cache()

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(main.repository, "list_observations", boom)
    resp = TestClient(app).get("/api/v1/insights/cross-sector")
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]
