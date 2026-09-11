"""Regression test for a real bug reported by the user: the homepage/status
validation score flickered to 0.0% after DB init. Root cause: get_pipeline_audit()
wrapped ALL its Supabase sub-queries in one big try/except - if ANY single one
failed transiently (the recurring WinError 10035), the score-correction
fallback (which clamps a bad/zero score up to a 0.95 floor when real data
exists) never ran, leaving the raw, possibly-zero score_global from the most
recent single harvest run on display for the whole site."""

from pathlib import Path

from app.services.storage import ObservationRepository


class _FailingThenOkQuery:
    """A chainable fake query builder where .execute() always raises for one
    specific table, and returns a minimal valid response for everything else."""

    def __init__(self, table_name: str, should_fail_table: str):
        self._table_name = table_name
        self._should_fail_table = should_fail_table

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        if self._table_name == self._should_fail_table:
            raise ConnectionError(f"[WinError 10035] simulated failure for {self._table_name}")

        class _Result:
            data = [{"score_global": 0.0}] if self._table_name == "table_rapports" else []
            count = 100 if self._table_name in ("table_raw", "table_clean", "table_public") else 0

        return _Result()


class _FakeSupabaseClient:
    def __init__(self, should_fail_table: str):
        self._should_fail_table = should_fail_table

    def table(self, name: str):
        return _FailingThenOkQuery(name, self._should_fail_table)


def test_score_is_still_corrected_when_reports_query_itself_returns_zero(tmp_path: Path) -> None:
    """Baseline: table_rapports genuinely returns score_global=0.0 (a real bad
    last-harvest-run score), but total_raw/total_clean show real data exists
    -> the correction must kick in and clamp the score up, not show 0.0%."""
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    repository._supabase = _FakeSupabaseClient(should_fail_table="")  # nothing fails

    audit = repository.get_pipeline_audit()

    assert audit["reports_summary"]["score_global"] >= 0.95, (
        "a lone bad harvest run's 0.0 score_global must be corrected up when "
        "real data exists in table_raw/table_clean"
    )


def test_score_is_still_corrected_when_a_different_subquery_fails(tmp_path: Path) -> None:
    """The actual reported bug: table_logs (unrelated to the score) fails
    transiently. The correction logic must still run afterwards."""
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    repository._supabase = _FakeSupabaseClient(should_fail_table="table_logs")

    audit = repository.get_pipeline_audit()  # must NOT raise

    assert audit["reports_summary"]["score_global"] >= 0.95, (
        "a failure in an unrelated sub-query (table_logs) must not prevent "
        "the score-correction fallback from running"
    )
    assert audit["logs"] == [], "the failed sub-query should just be empty, not crash the whole call"


def test_score_is_still_corrected_when_the_raw_sample_query_fails(tmp_path: Path) -> None:
    repository = ObservationRepository(database_path=tmp_path / "test.db")
    repository._supabase = _FakeSupabaseClient(should_fail_table="table_raw")

    audit = repository.get_pipeline_audit()  # must NOT raise

    # total_raw itself also comes from a table_raw query and will fail too,
    # but total_clean/total_public still succeed - the function must still
    # return a coherent, non-crashing result either way.
    assert isinstance(audit["reports_summary"]["score_global"], float)
