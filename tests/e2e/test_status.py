"""Patch 0024 — status: only measured values; no invented load chart."""


def test_no_fake_load_chart_or_optimal_claim(probe):
    probe.goto("#/status")
    probe.page.wait_for_function("!document.querySelector('#scheduler-body .skeleton')")
    assert probe.page.locator("#chart-load").count() == 0
    text = probe.page.inner_text("#app-main")
    assert "Optimale" not in text and "Optimal" not in text


def test_scheduler_card_shows_real_state(probe):
    probe.goto("#/status")
    probe.page.wait_for_selector("#sched-state")
    assert probe.page.inner_text("#sched-state") in {"ACTIF", "ACTIVE", "ARRÊTÉ", "STOPPED"}
    assert probe.page.inner_text("#sched-last")                      # "no run since startup" in a fresh server
    assert probe.page.inner_text("#sched-next")


def test_counts_and_score_are_honest_in_sqlite_mode(probe):
    probe.goto("#/status")
    probe.page.wait_for_function("!document.querySelector('#pipeline-cards-container .skeleton')")
    assert probe.page.inner_text("#status-val-score") == "—"         # not a fake 100%
    assert probe.page.inner_text("#raw-count-tag") == "—"            # unknown in SQLite, not "0"
    assert probe.page.inner_text("#public-count-tag").startswith("60")


def test_unreachable_api_shows_dashes(probe):
    probe.page.route("**/api/v1/health", lambda r: r.abort())
    probe.page.route("**/api/v1/pipeline/audit", lambda r: r.abort())
    probe.goto("#/status")
    probe.page.wait_for_function("!document.querySelector('#pipeline-cards-container .skeleton')")
    assert probe.page.inner_text("#public-count-tag") == "—"
    assert probe.page.inner_text("#status-val-score") == "—"
