"""Region list and indicator catalog come from two SQL views (supabase/aggregates_setup.sql), because
Supabase returns at most 1000 rows per request and the old row-sampling saw only the newest ones.
Until the views exist the old method keeps working."""
from app.services import storage
from app.services.storage import ObservationRepository

CAP = 1000


class _Q:
    def __init__(self, rows, missing=False):
        self._rows, self._missing, self._lo, self._hi = list(rows), missing, 0, CAP - 1

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, n): self._hi = n - 1; return self
    def range(self, lo, hi): self._lo, self._hi = lo, hi; return self
    @property
    def not_(self): return self
    def is_(self, *a, **k): return self

    def execute(self):
        if self._missing:
            raise RuntimeError("relation does not exist")
        chunk = self._rows[self._lo:self._hi + 1][:CAP]
        return type("R", (), {"data": chunk})()


class _Client:
    def __init__(self, views=None, table=None):
        self.views, self.table_rows = views, table or []

    def table(self, name):
        if name == "v_region_counts":
            return _Q(self.views["regions"] if self.views else [], missing=not self.views)
        if name == "v_catalog":
            return _Q(self.views["catalog"] if self.views else [], missing=not self.views)
        return _Q(self.table_rows)


def _repo(tmp_path, client):
    storage.invalidate_cache()
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo._supabase = client
    return repo


def test_regions_come_from_the_view_beyond_1000_rows(tmp_path):
    regions = [{"region": f"Town {i} (Prov)", "n": i + 1} for i in range(1500)] + [{"region": "national", "n": 9}]
    repo = _repo(tmp_path, _Client(views={"regions": regions, "catalog": []}))
    names = repo.list_regions()
    assert len(names) == 1500 and "national" not in names
    assert names[0] == "Town 1499 (Prov)"          # most observed first


def test_catalog_comes_from_the_view_with_exact_counts(tmp_path, monkeypatch):
    catalog = [{"secteur": "markets", "indicateur": f"Price {i}", "source_api": "WFP", "records": 3000 + i,
                "first_date": "2015-01-01", "last_date": "2026-06-01"} for i in range(1200)]
    repo = _repo(tmp_path, _Client(views={"regions": [], "catalog": catalog}))
    out = repo.catalog()
    assert len(out) == 1200                          # more than one 1000-row page
    assert out[5] == {"sector": "markets", "indicator": "Price 5", "source": "WFP", "records": 3005,
                      "first_date": "2015-01-01", "last_date": "2026-06-01"}


def test_without_the_views_the_old_method_still_works(tmp_path):
    rows = [{"secteur": "health", "indicateur": "Life expectancy", "source_api": "World Bank",
             "date_reference": "2023-01-01", "region": "Lac"}]
    repo = _repo(tmp_path, _Client(views=None, table=rows))
    assert repo.list_regions() == ["Lac"]
    storage.invalidate_cache()
    cat = repo.catalog()
    assert cat and cat[0]["indicator"] == "Life expectancy" and cat[0]["records"] >= 1
