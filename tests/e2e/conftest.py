"""End-to-end browser tests (Playwright + the real FastAPI app on a throw-away SQLite DB).

Skipped automatically when Playwright / Chromium are not installed, so the normal
`pytest` run on a laptop or on Render is unaffected:
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]

# Minimal stand-ins for the two CDN libraries: they let us run offline and
# record exactly what each chart was asked to draw.
CHART_STUB = """
window.__charts = [];
window.Chart = function (canvas, cfg) { this.cfg = cfg; window.__charts.push(cfg); };
window.Chart.prototype.destroy = function () {};
window.Chart.defaults = { font: {} };
"""
LUCIDE_STUB = "window.lucide = { createIcons() {} };"

SEED = r"""
from app.services.storage import ObservationRepository
from app.schemas import ObservationCreate
repo = ObservationRepository()
rows = []
sectors = ["agriculture", "health", "energy", "markets"]
regions = ["Logone Occidental", "Logone Oriental", "Lac", "Mayo-Kebbi Est", "Mayo-Kebbi Ouest"]
for i in range(60):
    rows.append(ObservationCreate(
        sector=sectors[i % 4], indicator=f"Indicateur {i % 7}", value=float(i) + 0.5, unit="u",
        reference_date=f"2024-{i % 12 + 1:02d}-{i % 27 + 1:02d}", country_code="TCD",
        region=regions[i % 5], source="World Bank", source_url="https://example.org",
        license="CC-BY 4.0", notes="seed"))
print(repo.upsert_many(rows))
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    db = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {
        **os.environ,
        "DATABASE_PATH": str(db),
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "COLLECTION_API_KEY": "e2e-admin-key",
    }
    subprocess.run([sys.executable, "-c", SEED], cwd=ROOT, env=env, check=True, capture_output=True)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{base}/api/v1/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("e2e server did not start")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


def pytest_collection_modifyitems(items):
    """Run browser tests last: Playwright's sync API keeps an event loop alive in
    this thread while its fixture is open, which breaks asyncio-based tests that
    would run after it."""
    items.sort(key=lambda it: "tests/e2e/" in str(it.fspath).replace("\\", "/"))


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # Chromium not installed
            pytest.skip(f"Chromium unavailable: {exc}")
        yield b
        b.close()


def _install_cdn_stubs(page, *, chart_ok: bool = True) -> None:
    def handler(route):
        url = route.request.url
        if "chart.js" in url:
            if chart_ok:
                route.fulfill(body=CHART_STUB, content_type="application/javascript")
            else:
                route.abort()
        elif "lucide" in url:
            route.fulfill(body=LUCIDE_STUB, content_type="application/javascript")
        elif "fonts.googleapis" in url or "fonts.gstatic" in url:
            route.fulfill(body="", content_type="text/css")
        else:
            route.continue_()

    page.route("**/*", handler)


class Probe:
    """A page plus the evidence collected while it ran."""

    def __init__(self, page, base):
        self.page = page
        self.base = base
        self.api_calls: list[str] = []
        self.page_errors: list[str] = []
        page.on("request", lambda r: self.api_calls.append(r.url.replace(base, "")) if "/api/" in r.url else None)
        page.on("pageerror", lambda e: self.page_errors.append(str(e)))

    def calls(self, fragment: str) -> int:
        return sum(1 for u in self.api_calls if fragment in u)

    def goto(self, hash_: str = "") -> None:
        self.page.goto(f"{self.base}/{hash_}")
        self.page.wait_for_load_state("networkidle")


@pytest.fixture
def probe(browser, server):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    _install_cdn_stubs(page)
    yield Probe(page, server)
    ctx.close()


@pytest.fixture
def probe_no_chart_cdn(browser, server):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    _install_cdn_stubs(page, chart_ok=False)
    yield Probe(page, server)
    ctx.close()
