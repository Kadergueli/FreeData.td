"""Every sector must exist everywhere: adding one (demography) must never leave a screen, a
route, a schedule or a translation behind."""
import asyncio
import re
import typing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents import DemographyAgent
from app.config import settings
from app.main import app
from app.schemas.observation import ObservationCreate
from app.services import scheduler as sched_mod
from app.services.cadence import SECTOR_CADENCE_DAYS
from app.services.storage import SECTOR_IDS, ObservationRepository

STATIC = Path(__file__).resolve().parents[1] / "app" / "static" / "js"


def test_nine_sectors_including_demography():
    assert len(SECTOR_IDS) == 9 and "demography" in SECTOR_IDS


def test_schema_cadence_and_scheduler_cover_every_sector():
    allowed = set(typing.get_args(ObservationCreate.model_fields["sector"].annotation))
    assert allowed == set(SECTOR_IDS)
    assert set(SECTOR_CADENCE_DAYS) == set(SECTOR_IDS)
    src = Path(sched_mod.__file__).read_text(encoding="utf-8")
    for sector in SECTOR_IDS:
        assert f'("{sector}", ' in src, f"{sector} is not run by the scheduler"


@pytest.mark.parametrize("sector", SECTOR_IDS)
def test_every_sector_has_a_collection_route(sector, monkeypatch):
    monkeypatch.setattr(settings, "collection_api_key", "k")
    r = TestClient(app).post(f"/api/v1/collection/{sector}")
    assert r.status_code == 401, f"/collection/{sector}: {r.status_code}"      # exists, and needs the key


@pytest.mark.parametrize("view", ["views/home.js", "views/sectors.js", "views/data.js", "views/api.js", "views/admin.js"])
def test_every_screen_lists_every_sector(view):
    text = (STATIC / view).read_text(encoding="utf-8")
    for sector in SECTOR_IDS:
        assert re.search(rf"['\"]{sector}['\"]", text), f"{view} does not list '{sector}'"


def test_home_counts_all_sectors():
    assert f"ALL_SECTOR_COUNT = {len(SECTOR_IDS)};" in (STATIC / "views/home.js").read_text(encoding="utf-8")


def test_sector_names_exist_in_both_languages():
    text = (STATIC / "i18n.js").read_text(encoding="utf-8")
    fr, en = text.split("\n  en: {", 1) if "\n  en: {" in text else (text[: len(text) // 2], text[len(text) // 2:])
    for sector in SECTOR_IDS:
        for part, lang in ((fr, "fr"), (en, "en")):
            assert re.search(rf"\b{sector}:\s+'[^']+'", part), f"no {lang} name for {sector}"
    assert "'DÉMOGRAPHIE'" in text and "'DEMOGRAPHY'" in text


def test_the_catalogue_lists_a_source_for_demography():
    text = (STATIC / "sources_catalog.js").read_text(encoding="utf-8")
    assert text.count("sectorId: 'demography'") >= 2 and "INSEED" in text


# ── the agent itself ──
def test_demography_demo_collection_is_stored(tmp_path):
    repo = ObservationRepository(database_path=tmp_path / "d.db")
    result = asyncio.run(DemographyAgent(repo).run("demo"))
    rows = repo.list_observations(sector="demography")
    assert result.stored == 3 and {r["sector"] for r in rows} == {"demography"}


def test_demography_unknown_source_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown source"):
        asyncio.run(DemographyAgent(ObservationRepository(database_path=tmp_path / "d.db")).collect("nope"))


def test_demography_reads_the_world_bank_answer(monkeypatch, tmp_path):
    from app.agents.base import BaseAgent
    seen = []

    async def fake_fetch(client, url, params=None, **kw):
        seen.append(url)
        return [{"page": 1}, [{"date": "2023", "value": 18278568}, {"date": "2022", "value": None}, {"date": "x", "value": 1}]]
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    records = asyncio.run(DemographyAgent(ObservationRepository(database_path=tmp_path / "d.db")).collect("world-bank"))
    assert len(seen) == len(DemographyAgent.WORLD_BANK_INDICATORS)
    assert all(r["year"] == 2023 and r["region"] == "national" for r in records) and len(records) == len(seen)
