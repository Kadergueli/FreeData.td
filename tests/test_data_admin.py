"""Patch D — correct / delete / restore published data, manage reports, manage the admin team."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import admin as admin_mod
from app import main as main_mod
from app.config import settings
from app.schemas import ObservationCreate
from app.security import rate_limiter
from app.services.admin_store import AdminStore
from app.services.data_admin import DataAdminStore
from app.services.quarantine import QuarantineStore
from app.services.storage import ObservationRepository
from tests.test_quarantine import FakeSupabase2

OWNER = "owner@example.org"
H = {"Authorization": "Bearer tok-owner"}
HA = {"Authorization": "Bearer tok-admin"}      # a regular (non-owner) administrator
HX = {"Authorization": "Bearer tok-stranger"}


def _obs(i=1, value=10.0, sector="environment", indicator=None, region="Lac"):
    return ObservationCreate(sector=sector, indicator=indicator or f"Rainfall total {i}", value=value, unit="mm",
                             reference_date="2024-01-01", region=region, source="NASA POWER", notes="n")


@pytest.fixture
def repo(tmp_path):
    r = ObservationRepository(tmp_path / "d.db")
    r.upsert_many([_obs(1), _obs(2, 20.0)])
    return r


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(main_mod, "repository", repo)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "admin_emails", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: {
        "tok-owner": OWNER, "tok-admin": "helper@example.org", "tok-stranger": "x@y.org"}.get(t))
    rate_limiter._requests.clear()
    AdminStore(repo).add_admin("helper@example.org", "admin", OWNER)
    with TestClient(main_mod.app) as c:
        c.repo, c.data = repo, DataAdminStore(repo)
        c.ids = {o["indicator"]: o["id"] for o in c.data.search()}
        yield c


# ── store: durability against the next harvest ──────────────────────────────
def test_corrected_value_survives_a_harvest_that_brings_the_same_source_value(repo):
    data = DataAdminStore(repo)
    oid = data.search(q="Rainfall total 1")[0]["id"]
    assert data.correct(oid, 99.0, OWNER, "sensor error")["value"] == 10.0
    repo.upsert_many([_obs(1, 10.0)])                                 # source still says 10
    assert data.get(oid)["value"] == 99.0
    repo.upsert_many([_obs(1, 11.0)])                                 # source revised its figure: new truth
    assert data.get(oid)["value"] == 11.0


def test_deleted_value_stays_deleted_until_the_source_changes_it(repo):
    data = DataAdminStore(repo)
    oid = data.search(q="Rainfall total 1")[0]["id"]
    assert data.delete(oid, OWNER, "duplicate of another series")["indicator"] == "Rainfall total 1"
    assert data.get(oid) is None
    repo.upsert_many([_obs(1, 10.0)])
    assert data.search(q="Rainfall total 1") == []                    # not silently re-published
    repo.upsert_many([_obs(1, 12.0)])
    assert data.search(q="Rainfall total 1")[0]["value"] == 12.0


def test_delete_archives_and_restore_brings_it_back_once(repo):
    data = DataAdminStore(repo)
    oid = data.search(q="Rainfall total 2")[0]["id"]
    data.delete(oid, OWNER, "mistake")
    arch = data.list_deleted()
    assert len(arch) == 1 and arch[0]["row"]["value"] == 20.0 and arch[0]["deleted_by"] == OWNER and arch[0]["reason"] == "mistake"
    assert data.restore(arch[0]["id"], OWNER)["value"] == 20.0
    assert data.search(q="Rainfall total 2")[0]["value"] == 20.0
    assert data.list_deleted() == [] and data.restore(arch[0]["id"], OWNER) is None


def test_unknown_id_is_none_everywhere(repo):
    data = DataAdminStore(repo)
    assert data.get(999) is None and data.correct(999, 1.0, OWNER, "x") is None and data.delete(999, OWNER, "x") is None


def test_search_filters_by_sector_and_text(repo):
    repo.upsert_many([_obs(3, sector="agriculture", indicator="Crop yield")])
    data = DataAdminStore(repo)
    assert [o["indicator"] for o in data.search(sector="agriculture")] == ["Crop yield"]
    assert len(data.search(q="rainfall")) == 2
    assert data.search(q="no such indicator") == []


def test_failure_to_remember_the_source_value_aborts_before_changing_anything(repo, monkeypatch):
    data = DataAdminStore(repo)
    oid = data.search(q="Rainfall total 1")[0]["id"]
    monkeypatch.setattr(QuarantineStore, "suppress", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
    with pytest.raises(RuntimeError):
        data.correct(oid, 99.0, OWNER, "x")
    with pytest.raises(RuntimeError):
        data.delete(oid, OWNER, "x")
    assert data.get(oid)["value"] == 10.0                              # untouched


def test_supabase_path_correct_delete_restore(tmp_path):
    repo = ObservationRepository(tmp_path / "s.db")
    repo._supabase = FakeSupabase2()
    repo.upsert_many([_obs(1)])
    pub = repo._supabase.tables["table_public"]
    # extend the fake with the two calls the store uses beyond the write path
    from tests.test_quarantine import FakeQuery2

    class Q(FakeQuery2):
        def delete(self): self.op = "delete"; return self
        def is_(self, col, val): self.filters.append((col, None)); return self

        def execute(self):
            if self.op == "delete":
                t = self.db.tables.setdefault(self.name, [])
                keep = [r for r in t if not all(r.get(c) == v for c, v in self.filters)]
                gone = [r for r in t if r not in keep]
                t[:] = keep
                return SimpleNamespace(data=gone)
            if self.name == "table_deleted_observations" and self.op == "insert":
                t = self.db.tables.setdefault(self.name, [])
                for row in ([self.payload] if isinstance(self.payload, dict) else self.payload):
                    t.append(dict(row, id=len(t) + 1, restored_at=None))
                return SimpleNamespace(data=self.payload)
            return super().execute()
    repo._supabase.table = lambda name: Q(repo._supabase, name)

    data = DataAdminStore(repo)
    oid = data.search()[0]["id"]
    assert data.correct(oid, 5.0, OWNER, "typo")["value"] == 10.0
    row = pub[0]
    assert row["valeur"] == 5.0 and row["approuve_par"] == OWNER and "typo" in row["notes_publiques"]
    assert data.delete(oid, OWNER, "dup") is not None and pub == []
    aid = data.list_deleted()[0]["id"]
    assert data.restore(aid, OWNER)["value"] == 5.0
    assert [r["valeur"] for r in repo._supabase.tables["table_public"]] == [5.0]


# ── endpoints: access ───────────────────────────────────────────────────────
def test_every_new_endpoint_needs_an_administrator(client):
    calls = [("get", "/data"), ("post", "/data/1/correct"), ("post", "/data/1/delete"), ("get", "/data/deleted"),
             ("post", "/data/deleted/1/restore"), ("get", "/reports"), ("post", "/reports/1/delete"),
             ("get", "/admins"), ("post", "/admins"), ("post", "/admins/remove")]
    for method, path in calls:
        assert getattr(client, method)(f"/api/v1/admin{path}").status_code == 401, path
        assert getattr(client, method)(f"/api/v1/admin{path}", headers=HX).status_code == 403, path
    assert len(client.data.search()) == 2                               # nothing was touched


def test_only_the_owner_manages_the_team(client):
    assert client.post("/api/v1/admin/admins", json={"email": "new@x.org"}, headers=HA).status_code == 403
    assert client.post("/api/v1/admin/admins/remove", json={"email": "helper@example.org"}, headers=HA).status_code == 403
    listing = client.get("/api/v1/admin/admins", headers=HA).json()
    assert listing["can_manage"] is False and {a["email"] for a in listing["admins"]} == {OWNER, "helper@example.org"}


# ── endpoints: data ─────────────────────────────────────────────────────────
def test_search_endpoint(client):
    assert len(client.get("/api/v1/admin/data?sector=environment", headers=H).json()["items"]) == 2
    assert client.get("/api/v1/admin/data?sector=nope", headers=H).status_code == 422
    assert len(client.get("/api/v1/admin/data?q=Rainfall%20total%202", headers=H).json()["items"]) == 1


def test_correct_endpoint_changes_value_and_audits_before_after(client):
    oid = client.ids["Rainfall total 1"]
    r = client.post(f"/api/v1/admin/data/{oid}/correct", json={"value": 3.5, "reason": "unit slip"}, headers=HA)
    assert r.status_code == 200
    assert client.data.get(oid)["value"] == 3.5 and "unit slip" in client.data.get(oid)["notes"]
    e = AdminStore(client.repo).list_audit()[0]
    assert e["action"] == "data_corrected" and e["admin_email"] == "helper@example.org"
    assert e["detail"]["before"] == 10.0 and e["detail"]["after"] == 3.5 and e["detail"]["reason"] == "unit slip"


def test_a_reason_is_mandatory_for_correct_and_delete(client):
    oid = client.ids["Rainfall total 1"]
    for body in ({"value": 1.0, "reason": ""}, {"value": 1.0, "reason": "  a "}):
        assert client.post(f"/api/v1/admin/data/{oid}/correct", json=body, headers=H).status_code == 422
    assert client.post(f"/api/v1/admin/data/{oid}/delete", json={"reason": " "}, headers=H).status_code == 422
    assert client.data.get(oid)["value"] == 10.0 and AdminStore(client.repo).list_audit() == []


def test_correct_with_a_non_finite_number_is_refused(client):
    oid = client.ids["Rainfall total 1"]
    r = client.post(f"/api/v1/admin/data/{oid}/correct", json={"value": "nan", "reason": "test case"}, headers=H)
    assert r.status_code in (422, 503) and client.data.get(oid)["value"] == 10.0


def test_delete_then_restore_through_the_api(client):
    oid = client.ids["Rainfall total 2"]
    assert client.post(f"/api/v1/admin/data/{oid}/delete", json={"reason": "wrong region"}, headers=H).status_code == 200
    assert client.data.get(oid) is None
    arch = client.get("/api/v1/admin/data/deleted", headers=H).json()["items"]
    assert len(arch) == 1 and arch[0]["reason"] == "wrong region"
    assert client.post(f"/api/v1/admin/data/deleted/{arch[0]['id']}/restore", headers=H).status_code == 200
    assert client.get("/api/v1/admin/data/deleted", headers=H).json()["items"] == []
    assert client.post(f"/api/v1/admin/data/deleted/{arch[0]['id']}/restore", headers=H).status_code == 404
    actions = [a["action"] for a in AdminStore(client.repo).list_audit()]
    assert actions[:2] == ["data_restored", "data_deleted"]


def test_unknown_ids_are_404(client):
    assert client.post("/api/v1/admin/data/9999/correct", json={"value": 1.0, "reason": "none"}, headers=H).status_code == 404
    assert client.post("/api/v1/admin/data/9999/delete", json={"reason": "none"}, headers=H).status_code == 404


def test_storage_failure_is_a_503_and_not_audited(client, monkeypatch):
    oid = client.ids["Rainfall total 1"]
    monkeypatch.setattr(DataAdminStore, "delete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
    assert client.post(f"/api/v1/admin/data/{oid}/delete", json={"reason": "cleanup"}, headers=H).status_code == 503
    assert AdminStore(client.repo).list_audit() == []


# ── endpoints: reports ──────────────────────────────────────────────────────
def test_reports_list_and_delete(client):
    sid = client.repo.save_study("health", "model-x", 12, "report text")
    items = client.get("/api/v1/admin/reports", headers=H).json()["items"]
    assert [i["id"] for i in items] == [sid] and items[0]["report"] == "report text"
    assert client.post(f"/api/v1/admin/reports/{sid}/delete", json={"reason": ""}, headers=H).status_code == 422
    assert client.post(f"/api/v1/admin/reports/{sid}/delete", json={"reason": "hallucinated figure"}, headers=H).status_code == 200
    assert client.get("/api/v1/admin/reports", headers=H).json()["items"] == []
    assert client.post(f"/api/v1/admin/reports/{sid}/delete", json={"reason": "again please"}, headers=H).status_code == 404
    assert AdminStore(client.repo).list_audit()[0]["action"] == "report_deleted"


# ── endpoints: team ─────────────────────────────────────────────────────────
def test_owner_adds_and_removes_an_admin_and_access_changes_immediately(client, monkeypatch):
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: {"tok-owner": OWNER, "tok-new": "new.admin@example.org"}.get(t))
    N = {"Authorization": "Bearer tok-new"}
    assert client.get("/api/v1/admin/me", headers=N).status_code == 403
    r = client.post("/api/v1/admin/admins", json={"email": "  New.Admin@Example.org "}, headers=H)
    assert r.status_code == 201 and r.json()["email"] == "new.admin@example.org"
    assert client.get("/api/v1/admin/me", headers=N).json() == {"email": "new.admin@example.org", "role": "admin"}
    assert client.post("/api/v1/admin/admins/remove", json={"email": "new.admin@example.org"}, headers=H).status_code == 200
    assert client.get("/api/v1/admin/me", headers=N).status_code == 403            # revoked at once
    actions = [a["action"] for a in AdminStore(client.repo).list_audit()]
    assert actions[:2] == ["admin_removed", "admin_added"]


def test_team_rules(client):
    for bad in ("", "no-at-sign", "a@b", "two@@x.org", "sp ace@x.org"):
        assert client.post("/api/v1/admin/admins", json={"email": bad}, headers=H).status_code == 422, bad
    assert client.post("/api/v1/admin/admins", json={"email": OWNER}, headers=H).status_code == 409          # already owner
    assert client.post("/api/v1/admin/admins/remove", json={"email": OWNER}, headers=H).status_code == 409   # permanent owner / self
    assert client.post("/api/v1/admin/admins/remove", json={"email": "ghost@x.org"}, headers=H).status_code == 404
    listing = client.get("/api/v1/admin/admins", headers=H).json()
    assert listing["can_manage"] is True
    assert listing["admins"][0] == {"email": OWNER, "role": "owner", "permanent": True}


def test_an_owner_added_in_the_table_cannot_remove_themselves(client, monkeypatch):
    AdminStore(client.repo).add_admin("second@example.org", "owner", OWNER)
    monkeypatch.setattr(admin_mod, "verify_access_token", lambda t: "second@example.org")
    r = client.post("/api/v1/admin/admins/remove", json={"email": "second@example.org"}, headers=H)
    assert r.status_code == 409 and AdminStore(client.repo).get_role("second@example.org") == "owner"
