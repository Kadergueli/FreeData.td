"""Patch 0029 — truncated exports are flagged; raw archive files are capped."""
import json

from fastapi.testclient import TestClient

from app import main
from app.agents.base import BaseAgent
from app.main import app


def test_export_header_only_when_cap_is_hit(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(main.repository, "list_observations", lambda **k: [{"id": i} for i in range(main.EXPORT_LIMIT)])
    assert client.get("/api/v1/export/json").headers.get("X-Export-Truncated") == "true"
    monkeypatch.setattr(main.repository, "list_observations", lambda **k: [{"id": 1}])
    assert "X-Export-Truncated" not in client.get("/api/v1/export/json").headers


class Dummy(BaseAgent):
    sector = "agriculture"
    name = "dummy"

    async def collect(self, source):
        return []

    def normalize(self, record):
        return None


def test_raw_archive_keeps_only_the_newest_files(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr("app.agents.base.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Dummy, "RAW_ARCHIVE_KEEP", 3)
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for i in range(6):                       # pre-existing old files
        f = raw / f"agriculture_old{i}_20200101T00000{i}.json"
        f.write_text("[]")
        os.utime(f, (1_000_000 + i, 1_000_000 + i))
    other = raw / "health_keep_20200101T000000.json"
    other.write_text("[]")
    from datetime import UTC, datetime
    Dummy(None)._archive_raw("new", [{"a": 1}], datetime.now(UTC))
    left = sorted(p.name for p in raw.glob("agriculture_*.json"))
    assert len(left) == 3 and any("_new_" in n for n in left)       # newest kept, incl. the one just written
    assert other.exists()                                           # other sectors untouched
    assert json.loads(next(p for p in raw.glob("agriculture_new_*.json")).read_text()) == [{"a": 1}]
