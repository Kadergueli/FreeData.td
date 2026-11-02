"""Supabase answers at most 1000 rows per request, whatever .limit() asks for.
list_observations() used to make one call, so every CSV/JSON export (and GET /observations?limit=5000)
silently stopped at 1000 rows. These tests use a fake client that enforces that cap."""

from pathlib import Path

from app.services.storage import ObservationRepository

SERVER_CAP = 1000


class _Result:
    def __init__(self, data):
        self.data = data


class _CappedQuery:
    def __init__(self, rows: list[dict], calls: list):
        self._rows, self._calls = rows, calls
        self._lo, self._hi = 0, None

    def select(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def or_(self, *a, **k): return self

    def gt(self, field, value):
        self._rows = [r for r in self._rows if r[field] > value]
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r[field] == value]
        return self

    def order(self, field, desc=False):
        self._rows = sorted(self._rows, key=lambda r: r[field], reverse=desc)
        return self

    def limit(self, n):
        self._lo, self._hi = 0, n - 1
        return self

    def range(self, lo, hi):
        self._lo, self._hi = lo, hi
        return self

    def execute(self):
        hi = self._hi if self._hi is not None else SERVER_CAP - 1
        chunk = self._rows[self._lo:hi + 1][:SERVER_CAP]          # the server cap
        self._calls.append(len(chunk))
        return _Result(chunk)


class _Client:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, _name):
        return _CappedQuery(list(self.rows), self.calls)


def _rows(n: int, sector: str = "markets") -> list[dict]:
    return [{
        "id": i, "secteur": sector, "indicateur": f"Indicator {i}", "valeur": float(i), "unite": "XAF",
        "date_reference": f"2020-01-{(i % 28) + 1:02d}", "region": f"Region {i % 7}", "source_api": "WFP",
        "date_publication": "2026-01-01", "pays": "TCD", "licence": "CC-BY 4.0",
    } for i in range(n)]


def _repo(tmp_path: Path, rows: list[dict]) -> ObservationRepository:
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo._supabase = _Client(rows)
    return repo


def test_more_than_1000_rows_come_back(tmp_path):
    repo = _repo(tmp_path, _rows(3200))
    got = repo.list_observations(sector="markets", limit=5000)
    assert len(got) == 3200
    assert len({o["id"] for o in got}) == 3200            # no page overlap, no skipped row


def test_limit_is_respected_across_pages(tmp_path):
    got = _repo(tmp_path, _rows(5000)).list_observations(sector="markets", limit=2500)
    assert len(got) == 2500


def test_small_limits_use_one_request(tmp_path):
    repo = _repo(tmp_path, _rows(5000))
    assert len(repo.list_observations(sector="markets", limit=120)) == 120
    assert len(repo._supabase.calls) == 1            # one request (limit + dedup margin)


def test_export_of_a_big_sector_is_complete_and_not_flagged(tmp_path):
    rows, truncated = _repo(tmp_path, _rows(32_000)).export_rows("markets", None, 50_000)
    assert len(rows) == 32_000
    assert truncated is False


def test_export_over_the_cap_is_flagged(tmp_path):
    rows, truncated = _repo(tmp_path, _rows(7000)).export_rows("markets", None, 5000)
    assert len(rows) == 5000
    assert truncated is True


# --- offset paging (API pages) -------------------------------------------------------------------

def test_offset_pages_cover_everything_once(tmp_path):
    repo = _repo(tmp_path, _rows(2300))
    seen, offset = [], 0
    while offset is not None:
        rows, offset = repo.list_observations_page(sector="markets", limit=1000, offset=offset)
        seen += [o["id"] for o in rows]
    assert len(seen) == 2300 and len(set(seen)) == 2300


def test_last_page_has_no_next_offset(tmp_path):
    rows, nxt = _repo(tmp_path, _rows(40)).list_observations_page(sector="markets", limit=100)
    assert len(rows) == 40 and nxt is None


def test_exactly_full_last_page_does_not_loop_forever(tmp_path):
    repo = _repo(tmp_path, _rows(200))
    rows, nxt = repo.list_observations_page(sector="markets", limit=100)
    assert len(rows) == 100 and nxt == 100
    rows, nxt = repo.list_observations_page(sector="markets", limit=100, offset=nxt)
    assert len(rows) == 100 and nxt is None


# --- full export: no cap, constant memory ----------------------------------------------------------

def test_iter_observations_returns_every_row_past_the_server_cap(tmp_path):
    repo = _repo(tmp_path, _rows(3500))
    got = list(repo.iter_observations("markets", None))
    assert len(got) == 3500 and len({o["id"] for o in got}) == 3500
    assert all(c <= SERVER_CAP for c in repo._supabase.calls)


def test_iter_observations_on_sqlite(tmp_path):
    from app.schemas import ObservationCreate
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    repo.PAGE_SIZE = 50
    repo.upsert_many([ObservationCreate(sector="health", indicator=f"I{i}", value=float(i), unit="u",
                                        reference_date="2024-01-01", source="Test", region="Lac") for i in range(130)])
    assert len(list(repo.iter_observations("health", None))) == 130
    assert len(list(repo.iter_observations("health", "Lac"))) == 130
    assert list(repo.iter_observations("energy", None)) == []
    rows, nxt = repo.list_observations_page(sector="health", limit=60, offset=0)
    assert len(rows) == 60 and nxt == 60
    rows2, _ = repo.list_observations_page(sector="health", limit=100, offset=nxt)
    assert len(rows2) == 70 and not {o["id"] for o in rows} & {o["id"] for o in rows2}
