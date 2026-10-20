"""Patch 0019 — static asset delivery: compression and revalidation headers."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_large_static_js_is_gzipped():
    r = client.get("/static/js/i18n.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_static_assets_revalidate_instead_of_no_store():
    r = client.get("/static/js/router.js")
    cc = r.headers["cache-control"]
    assert "no-cache" in cc and "no-store" not in cc


def test_index_is_served_with_revalidation():
    r = client.get("/")
    assert r.status_code == 200
    assert "no-store" not in r.headers["cache-control"]


def test_index_does_not_load_unpinned_cdn_or_chartjs_eagerly():
    html = client.get("/").text
    assert "@latest" not in html
    assert "chart.js" not in html  # loaded on demand by charts.js
    assert 'href="#/data"' in html
