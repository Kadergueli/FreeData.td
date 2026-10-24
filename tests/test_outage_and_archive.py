"""Patch 0035 — reliability: honest 503 on outage, log labels that fit the DB, chunked raw archive."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import storage
from app.services.storage import ObservationRepository, StorageUnavailable, _split_raw_records
from tests.test_supabase_write_path import FakeSupabase, _obs


class RawFake:
    """Records inserts into table_raw (dict payloads, as the real client accepts)."""
    def __init__(self):
        self.inserted = []

    def table(self, name):
        assert name == "table_raw"
        fake = self

        class Q:
            def insert(self, payload):
                fake.inserted.append(payload)
                self.n = len(fake.inserted)
                return self

            def execute(self):
                return SimpleNamespace(data=[{"id": 100 + self.n}])
        return Q()


def _repo(tmp_path, client):
    repo = ObservationRepository(tmp_path / "x.db")
    repo._supabase = client
    return repo


def test_raw_archive_is_split_and_returns_first_id(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_RAW_PART_BYTES", 300)
    fake = RawFake()
    repo = _repo(tmp_path, fake)
    records = [{"k": "x" * 50, "i": i} for i in range(30)]
    assert repo.store_raw_batch("environment", "NASA", records) == 101
    assert len(fake.inserted) > 1
    assert sum(p["nb_lignes"] for p in fake.inserted) == 30
    assert all(len(p["donnee_brute"]) == p["nb_lignes"] for p in fake.inserted)


def test_small_raw_archive_is_one_row_and_empty_is_one_row(tmp_path):
    assert len(_split_raw_records([{"a": 1}])) == 1
    assert _split_raw_records([]) == [[]]


def test_log_labels_fit_database_columns(tmp_path):
    repo = _repo(tmp_path, FakeSupabase())
    repo.upsert_many([_obs(i) for i in range(3)])
    logs = repo._supabase.tables["table_logs"]
    assert logs
    for row in logs:
        assert len(row["agent"]) <= 20
        assert len(row["regle_appliquee"]) <= 10
        assert len(row["type_operation"]) <= 50
        assert len(row["superviseur"]) <= 50


def test_outage_gives_503_on_api_and_exports(monkeypatch):
    from app import main
    storage.invalidate_cache()

    def boom(*a, **k):
        raise StorageUnavailable("down")

    monkeypatch.setattr(main.repository, "list_observations", boom)
    client = TestClient(app)
    for url in ("/api/v1/observations", "/api/v1/export/csv", "/api/v1/export/json"):
        resp = client.get(url)
        assert resp.status_code == 503, url
        assert resp.headers.get("retry-after") == "30"


def test_empty_supabase_is_a_real_empty_answer_not_an_outage(tmp_path):
    class Empty:
        def table(self, n):
            class Q:
                def __getattr__(self, name):
                    return lambda *a, **k: self
                def execute(self):
                    return SimpleNamespace(data=[])
            return Q()
    repo = _repo(tmp_path, Empty())
    assert repo.list_observations() == []


def test_empty_source_response_is_not_archived(tmp_path):
    fake = RawFake()
    assert _repo(tmp_path, fake).store_raw_batch("health", "x", []) is None
    assert fake.inserted == []
