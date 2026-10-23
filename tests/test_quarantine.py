"""Patch C — suspicious values are held back, reviewed by an administrator, then published (or not)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.agents import HealthAgent
from app.config import settings
from app.schemas import ObservationCreate
from app.security import rate_limiter
from app.services.admin_store import AdminStore
from app.services.harvest_runs import summarize_results
from app.services.quarantine import QuarantineStore
from app.services.storage import ObservationRepository
from tests.test_supabase_write_path import FakeQuery, FakeSupabase

OWNER = "owner@example.org"
H = {"Authorization": "Bearer tok-owner"}


def _obs(indicator="Rainfall total", value=10.0, unit="mm", sector="environment", region="Lac", date="2024-01-01"):
    return ObservationCreate(sector=sector, indicator=indicator, value=value, unit=unit, reference_date=date,
                             region=region, source="NASA POWER", source_url="https://example.org", notes="n")


def _flags(indicator, value, unit):
    agent = HealthAgent(None)
    return agent.process_data_science_rules([_obs(indicator, value, unit, sector="health")])[0].flags


# ── the domain rule no longer flags real data ───────────────────────────────
def test_mortality_rate_per_1000_is_not_a_violation():
    assert "SUPERVISOR_REVIEW" not in _flags("Under-5 mortality rate", 105.9, "per 1,000 live births")


def test_negative_inflation_is_not_a_violation():
    assert "SUPERVISOR_REVIEW" not in _flags("Inflation rate", -2.4, "%")


def test_impossible_percentages_are_still_caught():
    assert "SUPERVISOR_REVIEW" in _flags("Unemployment rate", 140.0, "%")
    assert "SUPERVISOR_REVIEW" in _flags("Relative humidity", 120.0, "%")
    assert "SUPERVISOR_REVIEW" in _flags("Air temperature", 80.0, "°C")
    assert "SUPERVISOR_REVIEW" in _flags("Crop yield", -3.0, "t/ha")


# ── holding (SQLite) ────────────────────────────────────────────────────────
@pytest.fixture
def repo(tmp_path):
    return ObservationRepository(tmp_path / "q.db")


def _suspicious(value=-5.0):
    """Negative yield: impossible, flagged by the pipeline."""
    return HealthAgent(None).process_data_science_rules([_obs("Crop yield", value, "t/ha", sector="agriculture")])


def test_suspicious_rows_are_held_not_published_and_clean_rows_are_published(repo):
    rows = _suspicious() + HealthAgent(None).process_data_science_rules([_obs("Rainfall total", 12.0, "mm")])
    report = {}
    assert repo.upsert_many(rows, report=report) == 1
    assert report["held"] == 1
    assert [o["indicator"] for o in repo.list_observations()] == ["Rainfall total"]
    held = QuarantineStore(repo).list()
    assert len(held) == 1 and held[0]["indicateur"] == "Crop yield" and held[0]["valeur"] == -5.0
    assert "SUPERVISOR_REVIEW" in held[0]["flags"] and held[0]["status"] == "pending"


def test_same_value_twice_is_one_pending_row_and_a_new_value_refreshes_it(repo):
    repo.upsert_many(_suspicious())
    repo.upsert_many(_suspicious())
    assert len(QuarantineStore(repo).list()) == 1
    repo.upsert_many(_suspicious(-9.0))
    items = QuarantineStore(repo).list()
    assert len(items) == 1 and items[0]["valeur"] == -9.0


def test_a_ruled_value_is_not_asked_again_but_a_different_one_is(repo):
    store = QuarantineStore(repo)
    repo.upsert_many(_suspicious())
    qid = store.list()[0]["id"]
    assert store.decide(qid, "rejected", OWNER, "bad sensor")
    repo.upsert_many(_suspicious())                                   # same rejected value
    assert store.list("pending") == []
    repo.upsert_many(_suspicious(-7.0))                               # new value: a new question
    assert [i["valeur"] for i in store.list("pending")] == [-7.0]


def test_decide_is_atomic(repo):
    store = QuarantineStore(repo)
    repo.upsert_many(_suspicious())
    qid = store.list()[0]["id"]
    assert store.decide(qid, "approved", OWNER) is True
    assert store.decide(qid, "rejected", "other@x.org") is False       # too late
    assert store.get(qid)["status"] == "approved" and store.get(qid)["reviewed_by"] == OWNER


def test_holding_failure_surfaces_instead_of_losing_rows(repo, monkeypatch):
    monkeypatch.setattr(QuarantineStore, "hold", lambda self, rows, raw: (_ for _ in ()).throw(RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        repo.upsert_many(_suspicious())
    assert repo.list_observations() == []                              # and nothing suspicious leaked out


def test_collection_result_and_run_summary_report_held(tmp_path):
    repo = ObservationRepository(tmp_path / "h.db")
    result = asyncio.run(HealthAgent(repo).run("demo"))                # demo data is all legitimate now
    assert result.held == 0 and result.stored == 3
    assert summarize_results({"health": {"stored": 2, "held": 4}})[1]["health"]["held"] == 4


# ── holding + publishing (Supabase, in-memory fake) ─────────────────────────
class FakeQuery2(FakeQuery):
    def __init__(self, db, name):
        super().__init__(db, name)
        self.upd, self.want_count, self.lim, self.order_desc = None, False, None, False

    def select(self, *_a, count=None): self.op, self.want_count = "select", bool(count); return self
    def update(self, payload): self.op, self.upd = "update", payload; return self
    def order(self, *_a, **_k): return self
    def limit(self, n): self.lim = n; return self

    def execute(self):
        table = self.db.tables.setdefault(self.name, [])
        if self.op == "update":
            hit = [r for r in table if all(r.get(c) == v for c, v in self.filters)]
            for r in hit:
                r.update(self.upd)
            return SimpleNamespace(data=[dict(r) for r in hit])
        if self.name == "table_quarantine" and self.op == "insert":
            for row in ([self.payload] if isinstance(self.payload, dict) else self.payload):
                table.append(dict(row, id=len(table) + 1, status="pending"))
            return SimpleNamespace(data=self.payload)
        res = super().execute()
        if self.op == "select":
            if self.lim:
                res.data = res.data[: self.lim]
            res.count = len(res.data)
        return res


class FakeSupabase2(FakeSupabase):
    def table(self, name): return FakeQuery2(self, name)


@pytest.fixture
def sb_repo(tmp_path):
    r = ObservationRepository(tmp_path / "s.db")
    r._supabase = FakeSupabase2()
    return r


def test_supabase_path_holds_then_publishes_with_the_reviewer_and_a_trace(sb_repo):
    sb_repo.upsert_many(_suspicious() + HealthAgent(None).process_data_science_rules([_obs("Rainfall total", 12.0, "mm")]))
    db = sb_repo._supabase
    assert [r["indicateur"] for r in db.tables["table_public"]] == ["Rainfall total"]
    store = QuarantineStore(sb_repo)
    item = store.list()[0]
    assert item["indicateur"] == "Crop yield" and store.counts()["pending"] == 1

    assert store.decide(item["id"], "corrected", OWNER, "typo", 5.0)
    sb_repo.publish_reviewed(item, 5.0, OWNER, "[Valeur corrigée par un administrateur : -5 -> 5]")
    pub = {r["indicateur"]: r for r in db.tables["table_public"]}
    assert pub["Crop yield"]["valeur"] == 5.0 and pub["Crop yield"]["approuve_par"] == OWNER
    assert "REVIEWED" in pub["Crop yield"]["notes_publiques"] and "SUPERVISOR_REVIEW" not in pub["Crop yield"]["notes_publiques"]
    assert "corrigée" in pub["Crop yield"]["notes_publiques"]
    assert store.counts() == {"pending": 0, "approved": 0, "corrected": 1, "rejected": 0}


# ── admin endpoints ─────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ObservationRepository(tmp_path / "a.db")
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: {"tok-owner": OWNER, "tok-stranger": "x@y.org"}.get(t))
    rate_limiter._requests.clear()
    repo.upsert_many(_suspicious())
    with TestClient(main_mod.app) as c:
        c.repo, c.store = repo, QuarantineStore(repo)
        c.qid = c.store.list()[0]["id"]
        yield c


def test_quarantine_endpoints_require_an_administrator(client):
    for method, path in (("get", "/quarantine"), ("post", f"/quarantine/{client.qid}/approve"),
                         ("post", f"/quarantine/{client.qid}/correct"), ("post", f"/quarantine/{client.qid}/reject")):
        assert getattr(client, method)(f"/api/v1/admin{path}").status_code == 401
        assert getattr(client, method)(f"/api/v1/admin{path}", headers={"Authorization": "Bearer tok-stranger"}).status_code == 403
    assert client.repo.list_observations() == [] and client.store.counts()["pending"] == 1


def test_list_shows_pending_with_counts(client):
    data = client.get("/api/v1/admin/quarantine", headers=H).json()
    assert data["counts"]["pending"] == 1 and data["items"][0]["indicateur"] == "Crop yield"
    assert client.get("/api/v1/admin/quarantine?status=bogus", headers=H).status_code == 422
    assert client.get("/api/v1/admin/quarantine?status=all", headers=H).status_code == 200


def test_approve_publishes_as_is_and_is_audited(client):
    r = client.post(f"/api/v1/admin/quarantine/{client.qid}/approve", json={"note": "confirmed on site"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert [o["value"] for o in client.repo.list_observations()] == [-5.0]
    row = client.store.get(client.qid)
    assert row["status"] == "approved" and row["reviewed_by"] == OWNER and row["review_note"] == "confirmed on site"
    entry = AdminStore(client.repo).list_audit()[0]
    assert entry["action"] == "quarantine_approved" and entry["admin_email"] == OWNER and "Crop yield" in entry["target"]


def test_correct_publishes_the_corrected_value(client):
    r = client.post(f"/api/v1/admin/quarantine/{client.qid}/correct", json={"value": 5.0, "note": "sign typo"}, headers=H)
    assert r.status_code == 200
    assert [o["value"] for o in client.repo.list_observations()] == [5.0]
    row = client.store.get(client.qid)
    assert row["status"] == "corrected" and row["corrected_value"] == 5.0 and row["valeur"] == -5.0   # original kept


def test_reject_publishes_nothing(client):
    assert client.post(f"/api/v1/admin/quarantine/{client.qid}/reject", headers=H).status_code == 200
    assert client.repo.list_observations() == []
    assert client.store.get(client.qid)["status"] == "rejected"
    assert AdminStore(client.repo).list_audit()[0]["action"] == "quarantine_rejected"


def test_second_review_is_a_conflict_and_unknown_id_is_404(client):
    assert client.post(f"/api/v1/admin/quarantine/{client.qid}/reject", headers=H).status_code == 200
    assert client.post(f"/api/v1/admin/quarantine/{client.qid}/approve", headers=H).status_code == 409
    assert client.repo.list_observations() == []                       # the rejection stands
    assert client.post("/api/v1/admin/quarantine/9999/approve", headers=H).status_code == 404


def test_non_finite_correction_is_refused_and_the_row_stays_pending(client):
    r = client.post(f"/api/v1/admin/quarantine/{client.qid}/correct", json={"value": "nan"}, headers=H)
    assert r.status_code == 422
    assert client.store.get(client.qid)["status"] == "pending" and client.repo.list_observations() == []


def test_publish_failure_puts_the_row_back_in_the_queue(client, monkeypatch):
    monkeypatch.setattr(ObservationRepository, "publish_reviewed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    r = client.post(f"/api/v1/admin/quarantine/{client.qid}/approve", headers=H)
    assert r.status_code == 503
    assert client.store.get(client.qid)["status"] == "pending"          # not stuck "approved but unpublished"
    assert AdminStore(client.repo).list_audit() == []


def test_overview_alerts_on_pending_quarantine(client):
    admin_mod._cache_set("admin_overview", None)
    o = client.get("/api/v1/admin/overview", headers=H).json()
    assert o["quarantine"]["pending"] == 1
    a = next(x for x in o["alerts"] if x["code"] == "quarantine_pending")
    assert a["level"] == "warning" and a["params"]["count"] == 1
    client.post(f"/api/v1/admin/quarantine/{client.qid}/reject", headers=H)
    o = client.get("/api/v1/admin/overview", headers=H).json()
    assert not any(x["code"] == "quarantine_pending" for x in o["alerts"])
