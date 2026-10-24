"""Patch 0039 — each source is judged on its newest measurement, not on when we last collected."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ObservationCreate
from app.services import storage
from app.services.freshness import SOURCE_MAX_AGE_DAYS, build_source_freshness, classify
from app.services.storage import ObservationRepository, StorageUnavailable

TODAY = date(2026, 10, 25)


def _row(sector, source, latest, published="2026-10-23 07:51:07", rows=10):
    return {"sector": sector, "source": source, "rows": rows, "latest_reference": latest, "last_published": published}


def test_classify_thresholds():
    assert classify(21, 21) == "ok" and classify(22, 21) == "late"
    assert classify(42, 21) == "late" and classify(43, 21) == "stale"
    assert classify(None, 21) == "stale"


def test_daily_collector_stuck_on_an_old_window_is_stale_even_though_it_ran_today():
    """Production, Oct 2026: Open-Meteo was 'collected' on 23 Oct but only returned data up to 2024-12-31."""
    rows = build_source_freshness([_row("environment", "Open-Meteo Archive", "2024-12-31", "2026-10-23 11:57:45")], TODAY)
    assert rows[0]["status"] == "stale" and rows[0]["age_days"] == 663
    assert rows[0]["last_published"] == "2026-10-23"


def test_annual_statistics_with_the_normal_lag_are_ok():
    rows = build_source_freshness([_row("health", "World Bank", "2024-01-01"), _row("education", "UNESCO UIS", "2019-01-01")], TODAY)
    by = {r["source"]: r["status"] for r in rows}
    assert by["World Bank"] == "ok" and by["UNESCO UIS"] == "stale"


def test_unknown_source_gets_a_default_and_worst_sources_come_first():
    rows = build_source_freshness([
        _row("a", "World Bank", "2024-01-01"),
        _row("b", "Mystery API", "2025-01-01"),
        _row("c", "Open-Meteo Archive", "2026-10-20"),
        _row("d", "Open-Meteo Transport", "2024-01-01"),
    ], TODAY)
    assert [r["status"] for r in rows] == sorted([r["status"] for r in rows], key={"stale": 0, "late": 1, "ok": 2}.get)
    assert rows[0]["source"] == "Open-Meteo Transport"
    assert next(r for r in rows if r["source"] == "Mystery API")["max_age_days"] == 400


def test_every_collector_source_has_an_expected_age():
    """A new source name must be added to the table, or it silently gets the yearly default."""
    for name in ("Open-Meteo Archive", "Open-Meteo Agro-Climate", "NASA POWER", "NASA FIRMS VIIRS", "World Bank"):
        assert name in SOURCE_MAX_AGE_DAYS


def _obs(source, ref):
    return ObservationCreate(sector="health", indicator="Life expectancy", value=53.0, unit="years",
                             reference_date=ref, country_code="TCD", region="national", source=source,
                             source_url="https://example.org", license="CC-BY 4.0", notes="n")


def test_sqlite_backend_and_endpoint(tmp_path, monkeypatch):
    from app import main
    storage.invalidate_cache()
    repo = ObservationRepository(tmp_path / "x.db")
    repo.upsert_many([_obs("World Bank", "2023-01-01"), _obs("World Bank", "2024-01-01")])
    monkeypatch.setattr(main, "repository", repo)
    body = TestClient(app).get("/api/v1/sources/freshness").json()
    (src,) = body["sources"]
    assert src["source"] == "World Bank" and src["rows"] == 2 and src["latest_reference"] == "2024-01-01"


def test_supabase_backend_uses_the_database_function(tmp_path):
    storage.invalidate_cache()
    calls = []

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[_row("health", "World Bank", "2024-01-01")])

    class Client:
        def rpc(self, name):
            calls.append(name)
            return Rpc()

    repo = ObservationRepository(tmp_path / "x.db")
    repo._supabase = Client()
    assert repo.source_freshness()[0]["source"] == "World Bank"
    repo.source_freshness()
    assert calls == ["source_freshness"]                     # second call served from the cache


def test_database_outage_is_a_503_not_an_empty_list(tmp_path, monkeypatch):
    from app import main
    storage.invalidate_cache()

    class Client:
        def rpc(self, name):
            raise ConnectionError("down")

    repo = ObservationRepository(tmp_path / "x.db")
    repo._supabase = Client()
    monkeypatch.setattr(storage, "_with_retry", lambda fn, **k: fn())
    monkeypatch.setattr(main, "repository", repo)
    resp = TestClient(app).get("/api/v1/sources/freshness")
    assert resp.status_code == 503 and resp.headers["retry-after"] == "30"
    with pytest.raises(StorageUnavailable):
        repo.source_freshness()
