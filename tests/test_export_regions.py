"""Regression: a CSV export came back with only the header line. Cause: the region filter was
accent-sensitive while the stored spellings are not uniform ("Guera", "Guéra", "Mongo (Guéra)",
"Ouaddai", "Abéché (Ouaddaï)"), and the Export page offered "Guéra" / "Ouaddaï" / "Tandjilé"."""
import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ObservationCreate
from app.security import rate_limiter
from app.services.storage import ObservationRepository, _region_like_pattern

SPELLINGS = ["Guera", "Guéra", "Mongo (Guéra)", "Ouaddai", "Abéché (Ouaddaï)", "Tandjile", "Laï (Tandjilé)",
             "N'Djamena", "N’Djamena (N’Djamena)", "Lac", "Bol (Lac)"]


def _seed(repo):
    repo.upsert_many([
        ObservationCreate(sector="health" if i % 2 else "demography", indicator=f"Ind {i}", value=float(i), unit="u",
                          reference_date=f"2024-01-{i + 1:02d}", source="Test", region=r)
        for i, r in enumerate(SPELLINGS)
    ])


@pytest.mark.parametrize("typed,expected", [
    ("Guera", {"Guera", "Guéra", "Mongo (Guéra)"}),
    ("Guéra", {"Guera", "Guéra", "Mongo (Guéra)"}),
    ("GUERA", {"Guera", "Guéra", "Mongo (Guéra)"}),
    ("Ouaddai", {"Ouaddai", "Abéché (Ouaddaï)"}),
    ("Ouaddaï", {"Ouaddai", "Abéché (Ouaddaï)"}),
    ("Tandjile", {"Tandjile", "Laï (Tandjilé)"}),
    ("Tandjilé", {"Tandjile", "Laï (Tandjilé)"}),
    ("N'Djamena", {"N'Djamena", "N’Djamena (N’Djamena)"}),
    ("Lac", {"Lac", "Bol (Lac)"}),
])
def test_region_filter_ignores_accents_case_and_apostrophes(tmp_path: Path, typed, expected):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    assert {r["region"] for r in repo.list_observations(region=typed, limit=100)} == expected


def test_wildcards_typed_by_the_user_do_not_match_everything(tmp_path: Path):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    assert repo.list_observations(region="Zzz", limit=100) == []
    assert _region_like_pattern("%") == "%%"          # the typed % is dropped, never a wildcard of its own
    assert _region_like_pattern("a\\b") == "%_b%"


def test_pattern_is_the_same_for_every_spelling():
    assert _region_like_pattern("Guera") == _region_like_pattern("Guéra") == _region_like_pattern("GUERA".lower().capitalize())


def test_supabase_receives_the_accent_insensitive_pattern(tmp_path: Path):
    calls = {}

    class Query:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def or_(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def ilike(self, column, pattern):
            calls["ilike"] = (column, pattern)
            return self
        def execute(self):
            class R: data = []
            return R()

    class Client:
        def table(self, name): return Query()

    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo._supabase = Client()
    repo.list_observations(region="Guéra", limit=10)
    assert calls["ilike"][0] == "region"
    assert calls["ilike"][1] == _region_like_pattern("Guera")


def _client(monkeypatch, repo):
    rate_limiter._requests.clear()
    monkeypatch.setattr("app.main.repository", repo)
    return TestClient(app)


@pytest.mark.parametrize("fmt", ["csv", "json", "xml"])
def test_export_with_region_has_rows_and_row_count_header(tmp_path: Path, monkeypatch, fmt):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    res = _client(monkeypatch, repo).get(f"/api/v1/export/{fmt}", params={"region": "Guéra"})
    assert res.status_code == 200
    assert res.headers["X-Export-Rows"] == "3"


def test_csv_export_rows_are_in_the_file(tmp_path: Path, monkeypatch):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    client = _client(monkeypatch, repo)
    for params in ({}, {"sector": "health"}, {"sector": "demography", "region": "Guera"}, {"region": "national"}):
        res = client.get("/api/v1/export/csv", params=params)
        rows = list(csv.DictReader(io.StringIO(res.text)))
        assert rows, params
        assert int(res.headers["X-Export-Rows"]) == len(rows)


def test_empty_selection_is_announced_not_silent(tmp_path: Path, monkeypatch):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    res = _client(monkeypatch, repo).get("/api/v1/export/csv", params={"region": "Atlantis"})
    assert res.status_code == 200 and res.headers["X-Export-Rows"] == "0"
    assert len(res.text.strip().splitlines()) == 1


def test_export_page_checks_the_row_count_before_saving():
    js = (Path(__file__).parent.parent / "app/static/js/views/api.js").read_text(encoding="utf-8")
    assert "X-Export-Rows" in js and "api.export_empty" in js
    i18n = (Path(__file__).parent.parent / "app/static/js/i18n.js").read_text(encoding="utf-8")
    assert i18n.count("export_empty:") == 2


def test_filename_stays_ascii_for_accented_regions(tmp_path: Path, monkeypatch):
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    _seed(repo)
    res = _client(monkeypatch, repo).get("/api/v1/export/csv", params={"region": "Ouaddaï"})
    assert res.status_code == 200
    assert 'filename="freedatatd-all-Ouaddai-export.csv"' in res.headers["content-disposition"]
