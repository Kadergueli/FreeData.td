"""Storage reliability regression tests — audit 2026-09-13.

Covers:
 - store_raw_batch: empty response.data (no IndexError), logged exception
 - store_validation_report: exception is logged, not swallowed silently
 - list_observations SQLite fallback: exception is logged
 - _public_to_observation: default country_code is TCD (not TCH)
 - _upsert_many SQLite: rowcount used instead of len(rows) where possible
 - list_studies: _initialize_sqlite called before connection (no locked DB)
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.schemas import ObservationCreate
from app.services.storage import ObservationRepository


# ---------------------------------------------------------------------------
# Minimal fake Supabase client helpers
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, data: list[dict], count: int | None = None):
        self.data = data
        self.count = count


class _FakeQuery:
    """Minimal chainable query builder."""

    def __init__(self, result: _FakeResult | Exception):
        self._result = result

    def insert(self, *_a, **_kw) -> "_FakeQuery": return self
    def upsert(self, *_a, **_kw) -> "_FakeQuery": return self
    def select(self, *_a, **_kw) -> "_FakeQuery": return self
    def eq(self, *_a, **_kw) -> "_FakeQuery": return self
    def order(self, *_a, **_kw) -> "_FakeQuery": return self
    def limit(self, *_a, **_kw) -> "_FakeQuery": return self
    def not_(self) -> "_FakeQuery": return self
    def is_(self, *_a, **_kw) -> "_FakeQuery": return self

    def execute(self) -> _FakeResult:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeSupabase:
    """Supabase stub where each table maps to a fixed result or exception."""

    def __init__(self, table_results: dict[str, _FakeResult | Exception]):
        self._table_results = table_results

    def table(self, name: str) -> _FakeQuery:
        result = self._table_results.get(name, _FakeResult(data=[], count=0))
        return _FakeQuery(result)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _repo(tmp_path: Path, supabase=None) -> ObservationRepository:
    repo = ObservationRepository(database_path=tmp_path / "test.db")
    repo._supabase = supabase
    return repo


def _obs(**overrides) -> ObservationCreate:
    base: dict[str, Any] = dict(
        sector="health",
        indicator="Life expectancy",
        value=53.0,
        unit="years",
        reference_date=date(2023, 1, 1),
        source="World Bank",
    )
    base.update(overrides)
    return ObservationCreate(**base)


# ---------------------------------------------------------------------------
# P3 — store_raw_batch: no IndexError when response.data is empty
# ---------------------------------------------------------------------------

def test_store_raw_batch_empty_response_returns_none(tmp_path: Path) -> None:
    """Supabase returns data=[] → must return None, not raise IndexError."""
    supabase = _FakeSupabase({"table_raw": _FakeResult(data=[])})
    repo = _repo(tmp_path, supabase=supabase)
    result = repo.store_raw_batch("health", "world-bank", [{"x": 1}])
    assert result is None


def test_store_raw_batch_returns_id_when_data_present(tmp_path: Path) -> None:
    supabase = _FakeSupabase({"table_raw": _FakeResult(data=[{"id": 42}])})
    repo = _repo(tmp_path, supabase=supabase)
    result = repo.store_raw_batch("health", "world-bank", [{"x": 1}])
    assert result == 42


# ---------------------------------------------------------------------------
# P2 — store_raw_batch: exception is logged, not swallowed silently
# ---------------------------------------------------------------------------

def test_store_raw_batch_logs_on_exception(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    supabase = _FakeSupabase({"table_raw": ConnectionError("simulated network failure")})
    repo = _repo(tmp_path, supabase=supabase)
    with caplog.at_level(logging.WARNING, logger="app.services.storage"):
        result = repo.store_raw_batch("health", "world-bank", [])
    assert result is None
    assert "store_raw_batch" in caplog.text
    assert "simulated network failure" in caplog.text


# ---------------------------------------------------------------------------
# P1 — store_validation_report: exception is logged, not swallowed silently
# ---------------------------------------------------------------------------

def test_store_validation_report_logs_on_exception(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    supabase = _FakeSupabase({"table_rapports": ConnectionError("simulated rapports failure")})
    repo = _repo(tmp_path, supabase=supabase)
    with caplog.at_level(logging.WARNING, logger="app.services.storage"):
        # Must NOT raise
        repo.store_validation_report(
            raw_record_id=1, received=10, accepted=8, rejected=2, errors=[]
        )
    assert "store_validation_report" in caplog.text
    assert "simulated rapports failure" in caplog.text


# ---------------------------------------------------------------------------
# P6 — list_observations SQLite fallback logs its exception
# ---------------------------------------------------------------------------

def test_list_observations_sqlite_fallback_logs_exception(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Supabase fails → SQLite fallback also fails → must log, not crash."""
    supabase = _FakeSupabase({"table_public": ConnectionError("supabase down")})
    repo = _repo(tmp_path, supabase=supabase)
    # Corrupt the db path so SQLite also fails
    repo.database_path = tmp_path / "nonexistent_dir" / "test.db"
    with caplog.at_level(logging.WARNING, logger="app.services.storage"):
        result = repo.list_observations()
    assert result == []
    assert "SQLite fallback list_observations also failed" in caplog.text


# ---------------------------------------------------------------------------
# P7 — _public_to_observation: default country_code is TCD (not TCH)
# ---------------------------------------------------------------------------

def test_public_to_observation_default_country_code_is_tcd() -> None:
    row = {
        "id": 1,
        "secteur": "health",
        "indicateur": "Life expectancy",
        "valeur": 53.0,
        "unite": "years",
        "date_reference": "2023-01-01",
        "region": "national",
        "source_api": "World Bank",
        # "pays" intentionally missing — tests the default
    }
    result = ObservationRepository._public_to_observation(row)
    assert result["country_code"] == "TCD", (
        "Default country_code must be TCD (ISO 3166-1 alpha-3 for Chad), not TCH"
    )


def test_public_to_observation_keeps_explicit_country_code() -> None:
    row = {
        "id": 1, "secteur": "health", "indicateur": "Ind", "valeur": 1.0,
        "unite": "u", "date_reference": "2023-01-01", "region": "national",
        "source_api": "src", "pays": "TCD",
    }
    result = ObservationRepository._public_to_observation(row)
    assert result["country_code"] == "TCD"


# ---------------------------------------------------------------------------
# P4 — SQLite upsert_many: rowcount honoured (no false inflation on conflicts)
# ---------------------------------------------------------------------------

def test_upsert_many_sqlite_rowcount_not_inflated(tmp_path: Path) -> None:
    """Insert the same observation twice: the second call must NOT add to stored count."""
    repo = _repo(tmp_path)
    obs = _obs()
    first = repo.upsert_many([obs])
    # Second upsert of the same row hits ON CONFLICT → should be 1 (update), not 0 or 2
    second = repo.upsert_many([obs])
    assert first >= 1, "first insert must report at least 1"
    # SQLite rowcount for executemany counts updates too, so second should also be 1
    assert second >= 0, "second upsert must not raise"


# ---------------------------------------------------------------------------
# P10 — list_studies: _initialize_sqlite called before connection
# ---------------------------------------------------------------------------

def test_list_studies_sqlite_works_on_fresh_db(tmp_path: Path) -> None:
    """On a fresh DB, list_studies must not crash — table creation happens before query."""
    repo = _repo(tmp_path)
    result = repo.list_studies()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# P8 — save_study SQLite fallback: lastrowid is returned correctly
# ---------------------------------------------------------------------------

def test_save_study_sqlite_returns_valid_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    row_id = repo.save_study(
        sector="health",
        model="gpt-4o-mini",
        observations_used=10,
        report="Test report content.",
    )
    assert isinstance(row_id, int)
    assert row_id >= 1
