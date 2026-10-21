"""Patch 0023 — repository: server search, honest chart, stale-response safety, collection."""
import json

OBS_NULL = [{"id": 1, "sector": "health", "indicator": "Taux X", "value": None, "unit": "%",
             "reference_date": "2024-01-01", "country_code": "TCD", "region": "Lac", "source": "WHO",
             "license": "CC-BY 4.0", "notes": "", "collected_at": "2024-01-01", "status": "validated"}]


def _wait_list(probe):
    probe.page.wait_for_selector("#obs-list-container .obs-card-item, #obs-list-container .card:not(#obs-loading-indicator)")


def test_header_shows_shown_over_real_total_and_load_more_pages_until_the_end(probe):
    probe.goto("#/data")
    _wait_list(probe)
    probe.page.wait_for_function("document.querySelector('#obs-count-header').textContent.includes('/ 60')")
    assert probe.page.locator(".obs-card-item").count() == 15
    probe.page.click("#btn-load-more")
    probe.page.wait_for_function("document.querySelectorAll('.obs-card-item').length === 40")
    probe.page.click("#btn-load-more")
    probe.page.wait_for_function("document.querySelectorAll('.obs-card-item').length === 60")
    assert not probe.page.is_visible("#btn-load-more")      # nothing left → button gone


def test_search_is_server_side_and_finds_rows_not_on_screen(probe):
    probe.goto("#/data")
    _wait_list(probe)
    probe.api_calls.clear()
    probe.page.fill("#search-obs", "Mayo-Kebbi Ouest")
    probe.page.wait_for_function("[...document.querySelectorAll('.obs-card-item')].every(c => c.textContent.includes('Mayo-Kebbi Ouest')) && document.querySelectorAll('.obs-card-item').length > 0")
    assert any("q=Mayo-Kebbi+Ouest" in u for u in probe.api_calls), probe.api_calls


def test_search_is_debounced(probe):
    probe.goto("#/data")
    _wait_list(probe)
    probe.api_calls.clear()
    probe.page.type("#search-obs", "Logone", delay=30)
    probe.page.wait_for_timeout(900)
    searches = [u for u in probe.api_calls if "q=" in u]
    assert 1 <= len(searches) <= 2, searches        # not one request per keystroke


def test_search_with_no_match_says_so_and_escapes_the_term(probe):
    probe.goto("#/data")
    _wait_list(probe)
    probe.page.fill("#search-obs", '<img src=x onerror=alert(1)>"')
    probe.page.wait_for_selector("text=Aucun résultat pour")
    assert probe.page.locator("#obs-list-container img").count() == 0   # rendered as text, not HTML
    assert not probe.page.is_visible("#btn-empty-harvest")               # a failed search is not "no data"


def test_search_box_is_not_prefilled_from_stale_state(probe):
    probe.goto("#/data")
    probe.page.fill("#search-obs", 'a"b')
    probe.page.click("#desktop-nav a[data-route=sectors]")
    probe.page.click("#desktop-nav a[data-route=data]")
    probe.page.wait_for_selector("#search-obs")
    assert probe.page.input_value("#search-obs") == ""
    assert 'value=""' in probe.page.eval_on_selector("#search-obs", "e => e.outerHTML")


def test_missing_value_is_a_dash_not_zero(probe):
    probe.page.route("**/api/v1/observations*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(OBS_NULL)))
    probe.goto("#/data")
    probe.page.wait_for_selector(".obs-card-item")
    card = probe.page.inner_text(".obs-card-item")
    assert "—" in card
    assert "\n0 " not in card and not card.strip().startswith("0")
    assert "TCD" in card


def test_slow_old_response_cannot_overwrite_newer_filter(probe):
    probe.page.add_init_script("""
      const _f = window.fetch;
      window.fetch = (u, o) => {
        const url = String(u);
        const slow = url.includes('/api/v1/observations') && !url.includes('sector=');
        return slow ? new Promise(r => setTimeout(r, 1500)).then(() => _f(u, o)) : _f(u, o);
      };
    """)
    probe.page.goto(f"{probe.base}/#/data")
    probe.page.wait_for_selector(".filter-sector-btn")
    probe.page.click('.filter-sector-btn[data-sector="health"]')      # fast request, resolves first
    probe.page.wait_for_function("[...document.querySelectorAll('.obs-card-item')].length > 0")
    probe.page.wait_for_timeout(2200)                                  # the slow "all sectors" reply arrives late
    sectors = probe.page.eval_on_selector_all(".obs-card-item", "els => els.map(e => e.textContent)")
    assert sectors and all("SANTÉ" in t.upper() or "HEALTH" in t.upper() for t in sectors)


def test_admin_only_sector_disables_collection(probe):
    probe.goto("#/data?sector=transport")
    probe.page.wait_for_selector("#btn-data-harvest")
    assert probe.page.is_disabled("#btn-data-harvest")
    assert probe.page.get_attribute("#btn-data-harvest", "title")
    probe.page.wait_for_selector("#obs-list-container .card")
    assert probe.page.locator("#btn-empty-harvest").count() == 0


def test_collect_targets_the_selected_sector_only(probe):
    posts = []
    probe.page.route("**/api/v1/collection/*", lambda r: (posts.append(r.request.url), r.fulfill(status=200, content_type="application/json", body='{"stored":3}')))
    probe.goto("#/data?sector=health")
    _wait_list(probe)
    probe.page.click("#btn-data-harvest")
    probe.page.wait_for_selector(".toast--success")
    assert len(posts) == 1 and "/collection/health" in posts[0]


def test_empty_sector_offers_collection_for_that_sector(probe):
    # 'environment' has no rows in the seed but is collectable.
    posts = []
    probe.page.route("**/api/v1/collection/*", lambda r: (posts.append(r.request.url), r.fulfill(status=200, content_type="application/json", body='{"stored":0}')))
    probe.goto("#/data?sector=environment")
    probe.page.wait_for_selector("#btn-empty-harvest")
    probe.page.click("#btn-empty-harvest")
    probe.page.wait_for_selector(".toast")
    assert len(posts) == 1 and "/collection/environment" in posts[0]
    assert probe.page.is_enabled("#btn-empty-harvest") or probe.page.locator("#btn-empty-harvest").count() == 1


def test_chart_plots_one_indicator_in_one_region(probe):
    probe.goto("#/data?sector=agriculture")
    probe.page.wait_for_function("window.__charts && window.__charts.length > 0")
    caption = probe.page.inner_text("#chart-caption")
    assert caption.startswith("Indicateur 0 · Logone Occidental")
    cfg_vals = probe.page.evaluate("window.__charts[window.__charts.length - 1].data.datasets[0].data")
    assert len(cfg_vals) == 3 and all(isinstance(v, (int, float)) for v in cfg_vals)


def test_indicator_select_switches_the_series(probe):
    probe.goto("#/data")
    probe.page.wait_for_selector("#chart-indicator-select", state="visible")
    options = probe.page.eval_on_selector_all("#chart-indicator-select option", "o => o.map(x => x.value)")
    assert len(options) == 2
    other = [o for o in options if o not in probe.page.inner_text("#chart-caption")][0]
    probe.page.select_option("#chart-indicator-select", other)
    assert probe.page.inner_text("#chart-caption").startswith(other)


def test_no_chart_when_nothing_to_plot(probe):
    probe.goto("#/data?sector=education")
    probe.page.wait_for_selector("#chart-section-card .chart-empty")
    assert probe.page.inner_text("#chart-caption") == ""
    assert probe.page.is_hidden("#chart-indicator-select")


def test_controls_expose_state_to_assistive_tech(probe):
    probe.goto("#/data?sector=energy")
    _wait_list(probe)
    assert probe.page.get_attribute('.filter-sector-btn[data-sector="energy"]', "aria-pressed") == "true"
    assert probe.page.get_attribute('.filter-sector-btn[data-sector="tous"]', "aria-pressed") == "false"
    assert probe.page.evaluate("document.querySelector('#btn-sort-toggle').tagName") == "BUTTON"
    probe.page.click("#btn-grid-toggle")
    assert probe.page.get_attribute("#btn-grid-toggle", "aria-pressed") == "true"
