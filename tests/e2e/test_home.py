"""Patch 0021 — home: real numbers, no duplicate listeners, no public collection."""
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
    assert probe.page.inner_text("#stat-sectors-count") == "04 / 09"  # seed: 4 sectors hold data
    assert probe.page.inner_text("#stat-validation-score") == "—"     # SQLite mode: no quality score is measured, so no fake 100%
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


def test_home_has_no_collection_button_and_never_posts_a_collection(probe):
    posts = []
    probe.page.on("request", lambda r: posts.append(r.url) if "/api/v1/collection/" in r.url else None)
    probe.goto()
    probe.page.wait_for_function("!document.querySelector('.stat-card .skeleton')")
    assert probe.page.locator("#btn-home-harvest").count() == 0
    assert "collecte en live" not in probe.page.inner_text("#app-main").lower()
    assert posts == []


def test_accordions_open_with_one_click(probe):
    probe.goto()
    probe.page.click("[data-accordion-trigger=mission]")
    assert probe.page.eval_on_selector("[data-accordion=mission]", "e => e.classList.contains('is-open')")
    probe.page.click("[data-accordion-trigger=mission]")
    assert not probe.page.eval_on_selector("[data-accordion=mission]", "e => e.classList.contains('is-open')")
