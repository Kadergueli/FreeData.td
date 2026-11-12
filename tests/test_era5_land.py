"""Copernicus ERA5-Land: hourly CSV zip -> complete monthly values, and the agent wiring."""
import asyncio
import io
import zipfile
from datetime import date, datetime, timedelta

import pytest

from app.agents import era5_land
from app.agents.environment import EnvironmentAgent
from app.config import settings
from app.services.storage import ObservationRepository


def make_zip(start: date, end_inclusive: date, tp_end: date | None = None) -> bytes:
    """Temperature: constant 300.15 K by day (27 C) with a 5 K daily swing; rain: 2 mm per day,
    accumulated from 00 UTC, the day total being stamped 00:00 of the next day."""
    t_rows, p_rows = ["valid_time,t2m,latitude,longitude"], ["valid_time,tp,latitude,longitude"]
    cur = datetime.combine(start, datetime.min.time())
    last = datetime.combine(end_inclusive, datetime.min.time()) + timedelta(hours=23)
    while cur <= last:
        t_rows.append(f"{cur:%Y-%m-%d %H:%M:%S},{300.15 + (5 if cur.hour == 15 else 0) - (5 if cur.hour == 4 else 0)},8.6,16.1")
        cur += timedelta(hours=1)
    cur = datetime.combine(start, datetime.min.time())
    p_last = datetime.combine(tp_end or end_inclusive, datetime.min.time()) + timedelta(hours=24)
    while cur <= p_last:
        p_rows.append(f"{cur:%Y-%m-%d %H:%M:%S},{0.002 if cur.hour == 0 else 0.002 * cur.hour / 24},8.6,16.1")
        cur += timedelta(hours=1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("t.csv", "\n".join(t_rows))
        z.writestr("p.csv", "\n".join(p_rows))
    return buf.getvalue()


def test_monthly_values_are_converted_and_complete_months_only():
    blob = make_zip(date(2026, 1, 1), date(2026, 3, 10), tp_end=date(2026, 3, 10))
    out = {(m["month"], m["kind"]): m["value"] for m in era5_land.monthly(era5_land.read_zip(blob))}
    assert set(m for m, _ in out) == {1, 2}                      # March is incomplete
    assert out[(1, "max")] == pytest.approx(32.0)                # 305.15 K
    assert out[(1, "min")] == pytest.approx(22.0)
    assert out[(1, "precip")] == pytest.approx(2.0)              # 0.002 m = 2 mm per day
    assert 26.5 < out[(1, "mean")] < 27.5


def test_requests_are_split_below_the_tested_size():
    parts = era5_land.chunks(date(2025, 6, 1), date(2026, 7, 8))
    assert len(parts) == 2 and all((b - a).days < 366 for a, b in parts)
    assert parts[0][1] + timedelta(days=1) == parts[1][0]
    req = era5_land.build_request(8.56, 16.08, date(2026, 1, 1), date(2026, 1, 31))
    assert req["data_format"] == "csv" and req["location"] == {"longitude": 16.08, "latitude": 8.56}


def test_agent_needs_a_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cdsapi_key", None)
    with pytest.raises(ValueError, match="CDSAPI_KEY"):
        asyncio.run(EnvironmentAgent(ObservationRepository(tmp_path / "e.db")).collect("copernicus-era5"))


def test_agent_collects_per_region_and_reports_a_failed_one(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cdsapi_key", "k")
    monkeypatch.setattr("app.agents.environment.recent_window", lambda months=12, lag_days=7: ("2026-01-01", "2026-02-28"))

    def fake(url, key, lat, lon, start, end):
        if lat > 20:
            raise RuntimeError("cost limits exceeded")
        return make_zip(start, end)

    monkeypatch.setattr(era5_land, "fetch_region_blob", fake)
    agent = EnvironmentAgent(ObservationRepository(tmp_path / "e.db"))
    records = asyncio.run(agent.collect("copernicus-era5"))
    assert {r["source"] for r in records} == {"Copernicus ERA5-Land"}
    assert {r["indicator"] for r in records} == {"Monthly mean temperature", "Monthly max temperature",
                                                 "Monthly min temperature", "Monthly precipitation"}
    assert "Bardaï (Tibesti)" not in {r["region"] for r in records}
    assert len(records) == 22 * 4 * 2
    assert any("Bardaï" in e and "cost limits" in e for e in agent.source_errors)
    obs = agent.normalize(records[0])
    assert obs.license == "Licence to use Copernicus Products" and "Copernicus" in obs.notes
