"""Patch 0022 — explorer: real counts, links, no invented health/uptime/sources numbers."""
import re


def _card(probe, sector):
    return probe.page.locator(f'.sector-item-card[data-sector="{sector}"]')


def test_cards_show_exact_counts_from_stats(probe):
    probe.goto("#/sectors")
    probe.page.wait_for_function("!document.querySelector('#sectors-list .skeleton')")
    for sec in ("agriculture", "health", "energy", "markets"):
        assert "15" in _card(probe, sec).inner_text(), sec        # seed: 15 rows per sector
    # a sector without rows is not a full card: it is listed under "coming soon"
    assert probe.page.locator("#sectors-list [data-sector=transport]").count() == 0
    assert probe.page.locator("#sectors-soon-list [data-sector=transport]").count() == 1
    assert probe.page.is_visible("#sectors-soon")
    assert "25%" in _card(probe, "agriculture").inner_text()       # 15 of 60


def test_no_invented_figures_remain(probe):
    probe.goto("#/sectors")
    probe.page.wait_for_function("!document.querySelector('.stat-value .skeleton')")
    text = probe.page.inner_text("#app-main")
    assert "99.9" not in text                       # fake uptime
    assert not re.search(r"\b(98|88|92|90|65|42|94)%", text)  # old hard-coded "health scores"
    # sources figure is the real catalogue size, not a literal 12
    n = probe.page.evaluate("import('/static/js/sources_catalog.js').then(m => m.OFFICIAL_SOURCES.length)")
    assert probe.page.inner_text("#stat-sources") == str(n)


def test_cards_are_real_links_and_open_the_filtered_repository(probe):
    probe.goto("#/sectors")
    probe.page.wait_for_selector('.sector-item-card[data-sector="health"]')
    assert probe.page.get_attribute('.sector-item-card[data-sector="health"]', "href") == "#/data?sector=health"
    probe.page.click('.sector-item-card[data-sector="health"]')
    probe.page.wait_for_selector("#obs-list-container")
    assert probe.page.locator(".filter-sector-btn.btn-cyan").first.get_attribute("data-sector") == "health"


def test_unknown_counts_are_dashes_not_zero(probe):
    probe.page.route("**/api/v1/stats", lambda r: r.abort())
    probe.page.route("**/api/v1/pipeline/audit", lambda r: r.abort())
    probe.goto("#/sectors")
    probe.page.wait_for_function("!document.querySelector('#sectors-list .skeleton')")
    assert _card(probe, "health").locator(".badge").inner_text().strip() == "—"
    assert probe.page.inner_text("#stat-val-score") == "—"
    assert probe.page.inner_text("#stat-regions") == "—"


def test_search_filters_and_reports_no_match(probe):
    probe.goto("#/sectors")
    probe.page.wait_for_function("!document.querySelector('#sectors-list .skeleton')")
    probe.page.fill("#search-sectors", "santé")
    assert probe.page.locator("#sectors-list > .card:visible").count() == 1
    probe.page.fill("#search-sectors", "zzzz")
    assert probe.page.locator("#sectors-list > .card:visible").count() == 0
    assert probe.page.is_visible("#sectors-no-match")


def test_regions_covered_counts_regions_in_data(probe):
    probe.goto("#/sectors")
    probe.page.wait_for_function("!document.querySelector('#stat-regions .skeleton')")
    assert probe.page.inner_text("#stat-regions") == "5 / 23"       # seed: 5 distinct regions
