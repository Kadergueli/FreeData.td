"""Regression test for the bug found via a real Windows run: a transient
network failure on ONE sector's Supabase query (httpx.ReadError / WinError
10035) used to raise all the way up to a 500 on GET /api/v1/catalog. catalog()
now skips the failing sector and returns whatever succeeded, matching the
graceful-degradation pattern already used by get_pipeline_audit()."""

from pathlib import Path

from app.services.storage import ObservationRepository


class _FakeQuery:
    """Mimics the chainable supabase-py query builder: .table().select()
    .eq().order().limit().execute() -> object with a `.data` list."""

    def __init__(self, sector: str, should_fail: set[str]):
        self._sector = sector
        self._should_fail = should_fail

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, _field, value):
        self._sector = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._sector in self._should_fail:
            raise ConnectionError(f"[WinError 10035] simulated non-blocking socket read failure for {self._sector}")

        class _Result:
            data = [
                {
                    "secteur": self._sector,
                    "indicateur": "Test indicator",
                    "source_api": "World Bank",
                    "date_reference": "2024-01-01",
                }
            ]

        return _Result()


class _FakeSupabaseClient:
    def __init__(self, should_fail: set[str]):
        self._should_fail = should_fail

    def table(self, _name: str):
        return _FakeQuery(sector="", should_fail=self._should_fail)


def test_catalog_skips_failing_sector_instead_of_raising(tmp_path: Path) -> None:
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    # Simulate exactly the observed bug: 'health' fails with a transient
    # network error, every other sector succeeds.
    repository._supabase = _FakeSupabaseClient(should_fail={"health"})

    result = repository.catalog()  # must NOT raise

    sectors_returned = {row["sector"] for row in result}
    assert "health" not in sectors_returned, "the failing sector should be skipped, not crash the whole call"
    assert "agriculture" in sectors_returned, "sectors that succeeded should still be returned"
    assert "energy" in sectors_returned


def test_catalog_returns_empty_list_if_every_sector_fails(tmp_path: Path) -> None:
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    repository._supabase = _FakeSupabaseClient(
        should_fail={"agriculture", "environment", "markets", "transport", "education", "economy", "health", "energy"}
    )

    result = repository.catalog()  # must NOT raise even if ALL sectors fail
    assert result == []
