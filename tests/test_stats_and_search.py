"""Patch 0020 — /api/v1/stats, server-side search `q`, region counts."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas import ObservationCreate
from app.services import storage
from app.services.storage import ObservationRepository, _clean_search_term


def _obs(sector, indicator, region, value=1.0, source="World Bank", date="2024-01-01"):
    return ObservationCreate(sector=sector, indicator=indicator, value=value, unit="u", reference_date=date,
                             country_code="TCD", region=region, source=source,
                             source_url="https://example.org", license="CC-BY 4.0", notes="")


@pytest.fixture
def repo(tmp_path: Path):
    r = ObservationRepository(database_path=tmp_path / "t.db")
    r._supabase = None
    r.upsert_many([
        _obs("agriculture", "Rendement du mil", "Lac", 1, date="2024-01-01"),
        _obs("agriculture", "Rendement du sorgho", "Lac", 2, date="2024-02-01"),
        _obs("health", "Mortalité infantile", "Logone Occidental", 3, source="WHO"),
        _obs("health", "Couverture vaccinale", "Logone Oriental", 4, source="WHO"),
        _obs("energy", "Accès à l'électricité", "national", 5),
    ])
    return r


def test_stats_counts_are_real_not_sampled(repo):
    s = repo.get_stats()
    assert s["total"] == 5
    assert s["sectors"]["agriculture"] == 2 and s["sectors"]["health"] == 2 and s["sectors"]["energy"] == 1
    assert s["sectors"]["transport"] == 0          # successful query: an empty sector is a true 0
    assert set(s["sectors"]) == set(storage.SECTOR_IDS)
    assert s["regions"]["Lac"] == 2
    assert "national" not in {k.lower() for k in s["regions"]}
    assert s["last_update"]


def test_stats_is_cached_and_invalidated_by_writes(repo):
    first = repo.get_stats()
    assert repo.get_stats() is first  # served from cache
    repo.upsert_many([_obs("markets", "Prix du riz", "Lac", 9)])
    assert repo.get_stats()["sectors"]["markets"] == 1


def test_search_matches_indicator_source_region_and_is_case_insensitive(repo):
    assert {o["indicator"] for o in repo.list_observations(q="rendement")} == {"Rendement du mil", "Rendement du sorgho"}
    assert len(repo.list_observations(q="who")) == 2
    assert len(repo.list_observations(q="LOGONE")) == 2


def test_search_combines_with_sector_filter(repo):
    rows = repo.list_observations(sector="health", q="vaccinale")
    assert [o["indicator"] for o in rows] == ["Couverture vaccinale"]
    assert repo.list_observations(sector="energy", q="vaccinale") == []


def test_search_treats_wildcards_and_quotes_literally(repo):
    assert repo.list_observations(q="%") == repo.list_observations()  # '%' is stripped, not a wildcard
    assert repo.list_observations(q="x'; DROP TABLE observations;--") == []
    assert repo.count_observations() == 5  # table intact


@pytest.mark.parametrize("raw,expected", [
    (None, None), ("", None), ("   ", None), ("a,b", "a b"), ("x(y)", "x y"),
    ("a.b", "a.b"), ("%_*", None), ("  mil   sorgho ", "mil sorgho"),
])
def test_clean_search_term(raw, expected):
    assert _clean_search_term(raw) == expected


def test_clean_search_term_is_length_capped():
    assert len(_clean_search_term("a" * 500)) == 100


class _Q:
    """Records the PostgREST calls so we can assert on the filter string."""
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def f(*a, **k): self.calls.append((name, a, k)); return self
        return f
    @property
    def not_(self): return self
    def execute(self):
        class R: data = []; count = 3
        return R()


class _C:
    def __init__(self): self.q = _Q()
    def table(self, name): return self.q


def test_supabase_or_filter_is_built_from_cleaned_term():
    r = ObservationRepository.__new__(ObservationRepository)
    r._supabase = _C()
    r.list_observations(q="mil, sorgho)")  # comma/paren would otherwise inject extra filter clauses
    or_calls = [c for c in r._supabase.q.calls if c[0] == "or_"]
    assert or_calls and "mil sorgho" in or_calls[0][1][0]
    assert "," not in or_calls[0][1][0].split("indicateur.ilike.")[1].split(",")[0]
    assert ")" not in or_calls[0][1][0]


def test_supabase_stats_omits_failed_sector_instead_of_reporting_zero():
    storage.invalidate_cache()
    r = ObservationRepository.__new__(ObservationRepository)

    class Flaky(_Q):
        def eq(self, col, val):
            self._sec = val
            return self
        def execute(self):
            if getattr(self, "_sec", None) == "health":
                raise ConnectionError("boom")
            return super().execute()

    class C:
        def table(self, name): return Flaky()

    r._supabase = C()
    s = r.get_stats()
    assert "health" not in s["sectors"] and s["sectors"]["agriculture"] == 3


def test_count_observations_does_not_ship_rows():
    r = ObservationRepository.__new__(ObservationRepository)
    r._supabase = _C()
    r.count_observations(sector="health")
    assert ("limit", (1,), {}) in r._supabase.q.calls


def test_api_endpoints(monkeypatch, repo):
    from app import main
    monkeypatch.setattr(main, "repository", repo)
    c = TestClient(main.app)
    assert c.get("/api/v1/stats").json()["total"] == 5
    assert len(c.get("/api/v1/observations?q=who").json()) == 2
    assert c.get("/api/v1/observations?q=" + "a" * 101).status_code == 422
