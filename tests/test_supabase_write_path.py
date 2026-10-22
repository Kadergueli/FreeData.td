"""Patch 0028 — Supabase write path: no re-insert of unchanged rows, chunked requests.

Uses an in-memory fake of the few supabase-py calls the repository makes.
"""
from types import SimpleNamespace

from app.schemas import ObservationCreate
from app.services import storage
from app.services.storage import ObservationRepository

PUBLIC_KEY = ("secteur", "source_api", "date_reference", "indicateur", "region")


class FakeQuery:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.in_filters, self.rng, self.op, self.payload, self.conflict = [], [], None, "select", None, None

    def select(self, *_a): self.op = "select"; return self
    def eq(self, col, val): self.filters.append((col, val)); return self
    def in_(self, col, vals): self.in_filters.append((col, set(vals))); return self
    def range(self, a, b): self.rng = (a, b); return self
    def insert(self, payload): self.op, self.payload = "insert", payload; return self
    def upsert(self, payload, on_conflict=None): self.op, self.payload, self.conflict = "upsert", payload, on_conflict; return self

    def execute(self):
        table = self.db.tables.setdefault(self.name, [])
        self.db.requests.append((self.name, self.op, len(self.payload) if self.payload else 0))
        if self.op == "insert":
            out = []
            for row in self.payload:
                row = dict(row, id=len(table) + 1)
                table.append(row)
                out.append(row)
            return SimpleNamespace(data=out)
        if self.op == "upsert":
            for row in self.payload:
                key = tuple(row[c] for c in PUBLIC_KEY)
                for i, old in enumerate(table):
                    if tuple(old[c] for c in PUBLIC_KEY) == key:
                        table[i] = dict(row, id=old["id"])
                        break
                else:
                    table.append(dict(row, id=len(table) + 1))
            return SimpleNamespace(data=self.payload)
        rows = [r for r in table if all(r.get(c) == v for c, v in self.filters)
                and all(r.get(c) in vs for c, vs in self.in_filters)]
        if self.rng:
            rows = rows[self.rng[0]:self.rng[1] + 1]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self):
        self.tables, self.requests = {}, []

    def table(self, name):
        return FakeQuery(self, name)


def _obs(i, value=None):
    return ObservationCreate(
        sector="agriculture", indicator=f"Indicateur {i}", value=float(i if value is None else value),
        unit="t/ha", reference_date="2024-01-01", country_code="TCD", region="Lac",
        source="World Bank", source_url="https://example.org", license="CC-BY 4.0", notes="n")


def _repo(tmp_path):
    repo = ObservationRepository(tmp_path / "x.db")
    repo._supabase = FakeSupabase()
    return repo


def test_second_identical_harvest_writes_nothing_new(tmp_path):
    repo = _repo(tmp_path)
    assert repo.upsert_many([_obs(i) for i in range(30)]) == 30
    db = repo._supabase
    clean_before, logs_before = len(db.tables["table_clean"]), len(db.tables["table_logs"])

    assert repo.upsert_many([_obs(i) for i in range(30)]) == 0          # nothing changed
    assert len(db.tables["table_clean"]) == clean_before                # no growth
    assert len(db.tables["table_logs"]) == logs_before
    assert len(db.tables["table_public"]) == 30


def test_only_new_or_changed_rows_are_written(tmp_path):
    repo = _repo(tmp_path)
    repo.upsert_many([_obs(i) for i in range(10)])
    batch = [_obs(i) for i in range(10)]
    batch[3] = _obs(3, value=999.0)                                     # changed value
    batch.append(_obs(50))                                              # brand new
    assert repo.upsert_many(batch) == 2
    db = repo._supabase
    assert len(db.tables["table_clean"]) == 12
    public = {r["indicateur"]: r["valeur"] for r in db.tables["table_public"]}
    assert public["Indicateur 3"] == 999.0 and "Indicateur 50" in public
    assert len(db.tables["table_public"]) == 11                          # upsert, no duplicate


def test_large_batches_are_sent_in_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_WRITE_CHUNK", 100)
    repo = _repo(tmp_path)
    assert repo.upsert_many([_obs(i) for i in range(250)]) == 250
    sizes = [n for (t, op, n) in repo._supabase.requests if t == "table_clean" and op == "insert"]
    assert sizes == [100, 100, 50]
    assert len(repo._supabase.tables["table_public"]) == 250
    # ids stay aligned with their rows across chunks
    clean_ids = {r["id"] for r in repo._supabase.tables["table_clean"]}
    assert {r["id_clean"] for r in repo._supabase.tables["table_public"]} == clean_ids


def test_if_existing_values_cannot_be_read_everything_is_written(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    repo.upsert_many([_obs(i) for i in range(5)])

    def broken(*a, **k):
        raise RuntimeError("select failed")

    monkeypatch.setattr(storage, "_with_retry", lambda op, **k: broken() if k.get("label") == "table_public existing values" else op())
    assert repo.upsert_many([_obs(i) for i in range(5)]) == 5            # old behaviour: never write less
