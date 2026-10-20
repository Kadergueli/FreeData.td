"""Patch 0021 — home: real numbers, no duplicate listeners, honest + sequential harvest."""
import json


def test_home_uses_light_endpoints_only(probe):
    probe.goto()
    probe.page.wait_for_function("!document.querySelector('#stat-obs-count .skeleton')")
    assert probe.calls("/api/v1/catalog") == 0          # heaviest endpoint no longer used here
    assert probe.calls("/api/v1/stats") == 1
    assert probe.calls("/api/v1/observations?limit=1") == 1
    assert probe.calls("/api/v1/pipeline/audit") == 1


def test_home_shows_real_totals_and_no_skeleton_left(probe):
    probe.goto()
    probe.page.wait_for_function("!document.querySelector('.stat-card .skeleton')")
    assert probe.page.inner_text("#stat-obs-count") == "60"          # seed: 60 observations
    assert probe.page.inner_text("#stat-sectors-count") == "04 / 08"  # seed: 4 sectors hold data
    assert probe.page.inner_text("#stat-validation-score").endswith("%")
    loc = probe.page.inner_text("#latest-location")
    assert "TCD" in loc and "TCH" not in loc  # real ISO code from the data, not a made-up default
    assert probe.page.inner_text("#home-last-update")                 # last-update line present


def test_unknown_numbers_are_dashes_not_invented(probe):
    probe.page.route("**/api/v1/stats", lambda r: r.abort())
    probe.page.route("**/api/v1/pipeline/audit", lambda r: r.abort())
    probe.goto()
    probe.page.wait_for_function("!document.querySelector('.stat-card .skeleton')")
    assert probe.page.inner_text("#stat-obs-count") == "—"
    assert probe.page.inner_text("#stat-sectors-count") == "—"
    assert probe.page.inner_text("#stat-validation-score") == "—"


def _mock_collection(probe, status_by_call=None, stored=7):
    seen = []

    def handler(route):
        seen.append(route.request.url)
        status = (status_by_call or {}).get(len(seen), 200)
        body = {"stored": stored} if status == 200 else {"detail": "Collection rate limit reached."}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    probe.page.route("**/api/v1/collection/*", handler)
    return seen


def test_accordions_still_open_with_one_click_after_a_harvest(probe):
    _mock_collection(probe)
    probe.goto()
    probe.page.click("#btn-home-harvest")
    probe.page.wait_for_selector(".toast--success")
    probe.page.click("[data-accordion-trigger=mission]")
    assert probe.page.eval_on_selector("[data-accordion=mission]", "e => e.classList.contains('is-open')")
    probe.page.click("[data-accordion-trigger=mission]")
    assert not probe.page.eval_on_selector("[data-accordion=mission]", "e => e.classList.contains('is-open')")


def test_harvest_runs_sectors_one_after_another(probe):
    order = []
    probe.page.on("request", lambda r: order.append(("start", r.url)) if "/api/v1/collection/" in r.url else None)
    probe.page.on("requestfinished", lambda r: order.append(("end", r.url)) if "/api/v1/collection/" in r.url else None)
    _mock_collection(probe)
    probe.goto()
    probe.page.click("#btn-home-harvest")
    probe.page.wait_for_selector(".toast--success")
    kinds = [k for k, _ in order]
    assert kinds == ["start", "end"] * 6, kinds  # never two in flight at once


def test_harvest_reports_real_outcome_and_stops_on_rate_limit(probe):
    dialogs = []
    probe.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    seen = _mock_collection(probe, status_by_call={3: 429})
    probe.goto()
    probe.page.click("#btn-home-harvest")
    probe.page.wait_for_selector(".toast--error")
    assert len(seen) == 3                      # stopped at the 429, did not hammer the rest
    assert dialogs == []                       # no blocking alert()
    assert "limite" in probe.page.inner_text(".toast--error").lower()
    assert probe.page.is_enabled("#btn-home-harvest")


def test_harvest_total_failure_is_not_reported_as_success(probe):
    probe.page.route("**/api/v1/collection/*", lambda r: r.fulfill(status=503, content_type="application/json", body='{"detail":"down"}'))
    probe.goto()
    probe.page.click("#btn-home-harvest")
    probe.page.wait_for_selector(".toast--error")
    assert probe.page.locator(".toast--success").count() == 0


def test_success_toast_summarises_stored_rows(probe):
    _mock_collection(probe, stored=7)
    probe.goto()
    probe.page.click("#btn-home-harvest")
    probe.page.wait_for_selector(".toast--success")
    assert "6/6" in probe.page.inner_text(".toast--success") and "42" in probe.page.inner_text(".toast--success")
