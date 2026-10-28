"""Patch 0036 — an unfiltered export shares its row cap between sectors."""
from app.services.storage import SECTOR_IDS, ObservationRepository


def _repo(sizes, calls=None):
    repo = ObservationRepository.__new__(ObservationRepository)

    def fake(sector=None, region=None, limit=100, q=None):
        if calls is not None:
            calls.append((sector, limit))
        return [{"sector": sector, "i": i} for i in range(min(limit, sizes.get(sector, 0)))]

    repo.list_observations = fake
    return repo


def test_one_huge_sector_cannot_fill_the_file():
    sizes = {s: 30 for s in SECTOR_IDS}
    sizes["environment"] = 100_000
    rows, truncated = _repo(sizes).export_rows(None, None, 5000)
    per = {s: sum(1 for r in rows if r["sector"] == s) for s in SECTOR_IDS}
    assert len(rows) <= 5000 and truncated is True
    assert all(per[s] == 30 for s in SECTOR_IDS if s != "environment")   # small sectors complete
    assert per["environment"] == 5000 - 30 * (len(SECTOR_IDS) - 1)                           # leftover goes to the big one


def test_everything_fits_means_not_truncated():
    rows, truncated = _repo({s: 100 for s in SECTOR_IDS}).export_rows(None, None, 5000)
    assert len(rows) == 100 * len(SECTOR_IDS) and truncated is False


def test_sector_filter_keeps_newest_rows_behaviour():
    calls = []
    rows, truncated = _repo({"health": 9000}, calls).export_rows("health", None, 5000)
    assert calls == [("health", 5000)] and len(rows) == 5000 and truncated is True


def test_all_means_unfiltered():
    calls = []
    _repo({}, calls).export_rows("all", None, 5000)
    assert {s for s, _ in calls} == set(SECTOR_IDS)


def test_never_exceeds_limit_when_all_sectors_are_large():
    rows, truncated = _repo({s: 10_000 for s in SECTOR_IDS}).export_rows(None, None, 5000)
    assert len(rows) == 5000 and truncated is True
