"""Patch 0024 — sources directory: real count, no fake "12/12 OK"."""


def test_sources_count_is_the_catalogue_size(probe):
    probe.goto("#/sources")
    probe.page.wait_for_selector(".source-directory-item")
    n = probe.page.evaluate("import('/static/js/sources_catalog.js').then(m => m.OFFICIAL_SOURCES.length)")
    assert probe.page.locator(".source-directory-item").count() == n
    text = probe.page.inner_text("#app-main")
    assert str(n) in probe.page.inner_text("#sources-count-label")
    assert "12/12" not in text
    assert "Verified Open Data Source" not in text


def test_search_filters_and_shows_no_match_message(probe):
    probe.goto("#/sources")
    probe.page.wait_for_selector(".source-directory-item")
    total = probe.page.locator(".source-directory-item").count()
    probe.page.fill("#search-sources-input", "zzzz-no-such-source")
    assert probe.page.locator(".source-directory-item:visible").count() == 0
    assert probe.page.is_visible("#sources-no-match")
    probe.page.fill("#search-sources-input", "")
    assert probe.page.locator(".source-directory-item:visible").count() == total
    assert not probe.page.is_visible("#sources-no-match")


def test_cards_are_folded_and_sector_filter_narrows_the_list(probe):
    probe.goto("#/sources")
    probe.page.wait_for_selector(".source-directory-item")
    assert probe.page.locator(".source-directory-item[open]").count() == 0
    total = probe.page.locator(".source-directory-item").count()
    probe.page.click("#sources-sector-filter [data-filter=transport]")
    shown = probe.page.locator(".source-directory-item:visible").count()
    assert 0 < shown < total
    probe.page.click(".source-directory-item:visible summary >> nth=0")
    assert probe.page.locator(".source-directory-item[open] a[target=_blank]").count() == 1
    probe.page.click("#sources-sector-filter [data-filter=all]")
    assert probe.page.locator(".source-directory-item:visible").count() == total
