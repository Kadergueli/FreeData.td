"""Patch 0025 — AI Insights: honest density chart, working buttons, error states."""


def _density(probe):
    return probe.page.evaluate("(window.__charts || []).filter(c => c.type === 'bar').map(c => c.data.labels)")


def test_density_uses_full_region_names_not_three_letter_merge(probe):
    probe.goto("#/insights")
    probe.page.wait_for_function("(window.__charts || []).some(c => c.type === 'bar')")
    labels = _density(probe)[-1]
    assert "Mayo-Kebbi Est" in labels and "Mayo-Kebbi Ouest" in labels      # were both merged into "MAY"
    assert "Logone Occidental" in labels and "Logone Oriental" in labels    # were both merged into "LOG"
    assert "TCH" not in labels


def test_density_for_one_sector_and_no_fake_fallback(probe):
    probe.goto("#/insights")
    probe.page.wait_for_function("(window.__charts || []).some(c => c.type === 'bar')")
    probe.page.click('.insights-tab-btn[data-sector="health"]')
    probe.page.wait_for_function(
        "(window.__charts.filter(c => c.type === 'bar').pop().data.datasets[0].data).reduce((a, b) => a + b, 0) === 15")
    total = probe.page.evaluate("(window.__charts.filter(c => c.type === 'bar').pop().data.datasets[0].data).reduce((a, b) => a + b, 0)")
    assert total == 15                                                      # seed: 15 health rows


def test_buttons_work_before_slow_requests_finish(probe):
    # Make cross-sector very slow: tabs and the library toggle must already respond.
    def slow(route):
        import time
        time.sleep(1.5)
        route.continue_()
    probe.page.route("**/api/v1/insights/cross-sector", slow)
    probe.page.goto(f"{probe.base}/#/insights")
    probe.page.wait_for_selector("#toggle-reports-library")
    probe.page.click("#toggle-reports-library")
    probe.page.wait_for_function("document.getElementById('reports-library-wrapper').style.display === 'none'")


def test_cross_sector_failure_shows_message_and_retry(probe):
    probe.page.route("**/api/v1/insights/cross-sector", lambda r: r.abort())
    probe.goto("#/insights")
    probe.page.wait_for_selector("#ds-insights-error")
    assert probe.page.is_visible("#btn-retry-ds-insights")


def test_revisit_resets_active_tab_to_all(probe):
    probe.goto("#/insights")
    probe.page.click('.insights-tab-btn[data-sector="health"]')
    probe.goto("#/sectors")
    probe.goto("#/insights")
    probe.page.wait_for_selector(".insights-tab-btn")
    assert probe.page.get_attribute('.insights-tab-btn[data-sector="all"]', "aria-pressed") == "true"
    seen = []
    probe.page.route("**/api/v1/studies*", lambda r: (seen.append(r.request.url), r.abort())[1]
                     if r.request.method == "POST" else r.continue_())
    probe.page.click("#btn-run-analysis")
    probe.page.wait_for_selector("#new-study-container .text-accent")
    assert seen and "sector=" not in seen[0]                        # "all", matching the highlighted tab


def test_clicking_inside_open_report_does_not_collapse_it(probe):
    probe.page.route("**/api/v1/studies?*", lambda r: r.fulfill(json={"studies": [{
        "id": "s1", "sector": "health", "created_at": "2026-01-02T10:00:00", "model": "m",
        "observations_used": 10, "report": "## Titre\n\nParagraphe de test", "is_stale": False}]}))
    probe.goto("#/insights")
    probe.page.wait_for_selector(".study-library-row")
    probe.page.click(".study-library-row .flex")                    # header opens it
    probe.page.wait_for_selector(".study-library-detail .report-content", state="visible")
    probe.page.click(".study-library-detail .report-paragraph")     # inside the report
    assert probe.page.is_visible(".study-library-detail .report-content")
    probe.page.click(".study-library-row .flex.justify-between")    # header closes it
    assert not probe.page.is_visible(".study-library-detail .report-content")


def test_generation_timeout_message_is_translated(probe):
    probe.page.route("**/api/v1/studies*", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    probe.goto("#/insights")
    probe.page.wait_for_selector("#btn-run-analysis")
    probe.page.click("#btn-run-analysis")
    probe.page.wait_for_selector("#new-study-container .text-accent")
    assert "undefined" not in probe.page.inner_text("#new-study-container")
    assert probe.page.is_enabled("#btn-run-analysis")               # button restored after failure
