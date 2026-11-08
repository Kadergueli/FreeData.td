"""Patch 0019 — static asset delivery: compression and revalidation headers."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import SECTOR_IDS

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
    assert 'href="/static/favicon.svg"' in html
    assert 'itemtype="https://schema.org/DataCatalog"' in html


def test_favicon_and_discoverability_endpoints():
    for path, ctype in (
        ("/favicon.ico", "image/x-icon"),
        ("/static/favicon.ico", "image/x-icon"),
        ("/static/favicon.png", "image/png"),
        ("/static/icon-192.png", "image/png"),
        ("/static/icon-512.png", "image/png"),
        ("/static/icon-maskable-512.png", "image/png"),
        ("/static/favicon.svg", "image/svg+xml"),
        ("/manifest.webmanifest", "application/manifest+json"),
        ("/sw.js", "application/javascript"),
        ("/sitemap.xml", "application/xml"),
        ("/robots.txt", "text/plain"),
        ("/api/v1/catalog.jsonld", "application/ld+json"),
        ("/api/v1/catalog.dcat.json", "application/ld+json"),
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert ctype in r.headers["content-type"], (path, r.headers["content-type"])
        assert len(r.content) > 50, path

    jsonld = client.get("/api/v1/catalog.jsonld").json()
    assert jsonld["@type"] == "DataCatalog"
    assert len(jsonld["dataset"]) == len(SECTOR_IDS)

    dcat = client.get("/api/v1/catalog.dcat.json").json()
    assert dcat["@type"] == "dcat:Catalog"
    assert len(dcat["dcat:dataset"]) == len(SECTOR_IDS)


def test_public_read_endpoints_emit_cdn_cache_control_and_health_is_no_store():
    obs = client.get("/api/v1/observations?limit=5")
    assert obs.status_code == 200
    assert obs.headers.get("cache-control") == "public, max-age=3600"

    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    assert stats.headers.get("cache-control") == "public, max-age=3600"

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.headers.get("cache-control") == "no-store"

