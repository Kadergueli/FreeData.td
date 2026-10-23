"""Patch A — AdminStore against the Supabase API shape (in-memory fake of the calls it makes)."""
from types import SimpleNamespace

from app.services.admin_store import AdminStore
from app.services.storage import ObservationRepository


class Q:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.f, self.lim, self.op, self.payload, self.desc, self.conflict = [], None, "select", None, None, None

    def select(self, *_): return self
    def eq(self, c, v): self.f.append((c, v)); return self
    def limit(self, n): self.lim = n; return self
    def order(self, col, desc=False): self.desc = (col, desc); return self
    def insert(self, p): self.op, self.payload = "insert", p; return self
    def upsert(self, p, on_conflict=None): self.op, self.payload, self.conflict = "upsert", p, on_conflict; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        t = self.db.setdefault(self.name, [])
        if self.op == "insert":
            t.append(dict(self.payload, id=len(t) + 1, created_at=f"2026-10-23T10:00:{len(t):02d}"))
            return SimpleNamespace(data=[t[-1]])
        if self.op == "upsert":
            for r in t:
                if r[self.conflict] == self.payload[self.conflict]:
                    r.update(self.payload)
                    return SimpleNamespace(data=[r])
            t.append(dict(self.payload, created_at="2026-10-23T09:00:00"))
            return SimpleNamespace(data=[t[-1]])
        rows = [r for r in t if all(r.get(c) == v for c, v in self.f)]
        if self.op == "delete":
            for r in rows:
                t.remove(r)
            return SimpleNamespace(data=rows)
        if self.desc:
            rows = sorted(rows, key=lambda r: r[self.desc[0]], reverse=self.desc[1])
        return SimpleNamespace(data=rows[: self.lim] if self.lim else rows)


class FakeSB:
    def __init__(self): self.db = {}
    def table(self, name): return Q(self.db, name)


def _store(tmp_path):
    repo = ObservationRepository(tmp_path / "a.db")
    repo._supabase = FakeSB()
    return AdminStore(repo)


def test_admin_roles_roundtrip(tmp_path):
    s = _store(tmp_path)
    assert s.get_role("Nobody@x.org") is None
    s.add_admin("Second@X.org", "admin", "owner@x.org")
    assert s.get_role("second@x.org") == "admin"                  # e-mails are case-insensitive
    s.add_admin("second@x.org", "owner", "owner@x.org")           # promote = upsert, no duplicate
    assert s.get_role("second@x.org") == "owner" and len(s.list_admins()) == 1
    assert s.remove_admin("second@x.org") is True and s.get_role("second@x.org") is None
    assert s.remove_admin("second@x.org") is False


def test_invalid_role_is_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        _store(tmp_path).add_admin("a@x.org", "root", "o")


def test_audit_is_newest_first_and_never_raises(tmp_path):
    s = _store(tmp_path)
    s.log("a@x.org", "login")
    s.log("a@x.org", "observation.delete", "obs:12", {"reason": "typo"})
    entries = s.list_audit(10)
    assert [e["action"] for e in entries] == ["observation.delete", "login"]
    assert entries[0]["detail"] == {"reason": "typo"}

    class Broken:
        def table(self, *_): raise RuntimeError("db down")
    s.repository._supabase = Broken()
    s.log("a@x.org", "login")                                     # audit outage must not crash the admin action


def test_sqlite_fallback_for_development(tmp_path):
    s = AdminStore(ObservationRepository(tmp_path / "dev.db"))
    s.add_admin("dev@x.org", "owner", "env")
    assert s.get_role("dev@x.org") == "owner"
    s.log("dev@x.org", "login", None, {"ip": "1"})
    assert s.list_audit(5)[0]["detail"] == {"ip": "1"}
