"""Patch 0019 — shell: hash routing, single initial render, resilient charts, accessible nav."""


def test_home_loads_each_api_once(probe):
    probe.goto()
    # Previously the router and the language switch both rendered the home view,
    # so every endpoint was hit twice on a cold load.
    assert probe.calls("/api/v1/pipeline/audit") == 1, probe.api_calls
    assert probe.page_errors == []


def test_nav_tabs_are_links_with_aria_current(probe):
    probe.goto()
    tabs = probe.page.locator("#desktop-nav a.nav-tab")
    assert tabs.count() == 7
    assert probe.page.locator("#desktop-nav a.nav-tab[aria-current=page]").count() == 1
    assert probe.page.get_attribute("#desktop-nav a[data-route=data]", "href") == "#/data"


def test_click_updates_url_and_back_button_works(probe):
    probe.goto()
    probe.page.click("#desktop-nav a[data-route=sources]")
    probe.page.wait_for_selector("#sources-catalog-container")
    assert probe.page.url.endswith("#/sources")
    probe.page.click("#desktop-nav a[data-route=api]")
    probe.page.wait_for_selector("#btn-generate-archive")
    probe.page.go_back()
    probe.page.wait_for_selector("#sources-catalog-container")
    assert probe.page.url.endswith("#/sources")


def test_deep_link_and_refresh_keep_the_page(probe):
    probe.goto("#/data?sector=health")
    probe.page.wait_for_selector("#obs-list-container")
    active = probe.page.locator(".filter-sector-btn.btn-cyan").first.get_attribute("data-sector")
    assert active == "health"
    probe.page.reload()
    probe.page.wait_for_selector("#obs-list-container")
    assert probe.page.url.endswith("#/data?sector=health")


def test_unknown_hash_falls_back_to_home(probe):
    probe.goto("#/does-not-exist")
    probe.page.wait_for_selector("#btn-explore")


def test_language_toggle_rerenders_without_changing_url(probe):
    probe.goto("#/sources")
    probe.page.wait_for_selector("#sources-catalog-container")
    before = probe.page.inner_text("#desktop-nav a[data-route=insights]")
    probe.page.click("#lang-toggle")
    probe.page.wait_for_timeout(300)
    after = probe.page.inner_text("#desktop-nav a[data-route=insights]")
    assert before != after
    assert probe.page.url.endswith("#/sources")


def test_missing_chart_library_never_blanks_the_app(probe_no_chart_cdn):
    p = probe_no_chart_cdn
    p.goto("#/data")
    p.page.wait_for_selector("#obs-list-container .obs-card-item")
    # The page works, the chart area explains itself.
    assert p.page.locator("#desktop-nav a.nav-tab").count() == 7
    p.page.wait_for_selector("#chart-section-card .chart-empty")
    assert p.page_errors == []


def test_empty_sector_chart_shows_message_not_invented_data(probe):
    probe.goto("#/data?sector=education")  # no education rows in the seed
    probe.page.wait_for_selector("#chart-section-card .chart-empty")
    # Chart.js is not even requested when there is nothing to draw.
    assert probe.page.evaluate("(window.__charts || []).length") == 0


def test_chart_is_drawn_oldest_to_newest_when_data_exists(probe):
    probe.goto("#/data?sector=agriculture")
    probe.page.wait_for_function("window.__charts && window.__charts.length > 0")
    labels = probe.page.evaluate("window.__charts[window.__charts.length - 1].data.labels")
    assert labels == sorted(labels) and len(labels) > 1
