"""Patch 0024 — export & API: safe downloads, no fake key, real limits/status."""
import json


def test_no_fake_api_key_and_real_limits(probe):
    probe.goto("#/api")
    probe.page.wait_for_function("!document.querySelector('#api-limits-msg .skeleton')")
    # The measured latency can legitimately read any number (even 42 ms): exclude it from the check.
    text = probe.page.evaluate(
        "(() => { const c = document.querySelector('#app-main').cloneNode(true);"
        " c.querySelector('#api-latency-line')?.remove(); return c.innerText; })()")
    assert "fd_" not in text and "5 000" not in text and "42ms" not in text.replace(" ", "")
    health = json.loads(probe.page.evaluate("fetch('/api/v1/health').then(r => r.text())"))
    lim = health["limits"]
    msg = probe.page.inner_text("#api-limits-msg")
    assert str(lim["collection_per_hour"]) in msg and str(lim["analysis_per_hour"]) in msg
    assert "curl" in probe.page.inner_text("#api-examples")


def test_status_and_latency_are_measured(probe):
    probe.goto("#/api")
    probe.page.wait_for_function("document.querySelector('#api-latency-line')?.textContent.includes('ms')")
    assert probe.page.inner_text("#api-latency-line").split(":")[1].strip().endswith("ms")


def test_failed_download_shows_toast_and_saves_nothing(probe):
    probe.page.route("**/api/v1/export/**", lambda r: r.fulfill(
        status=503, content_type="application/json", body='{"detail":"parquet indisponible"}'))
    probe.goto("#/api")
    probe.page.wait_for_selector("#btn-generate-archive")
    downloads = []
    probe.page.on("download", lambda d: downloads.append(d))
    probe.page.click("#btn-generate-archive")
    probe.page.wait_for_selector(".toast")
    assert "parquet indisponible" in probe.page.inner_text(".toast")
    assert downloads == []
    assert not probe.page.is_disabled("#btn-generate-archive")      # button restored


def test_successful_download_uses_server_filename(probe):
    probe.goto("#/api")
    probe.page.wait_for_selector("#btn-generate-archive")
    probe.page.click('.export-fmt-btn[data-fmt="CSV"]')
    with probe.page.expect_download() as dl:
        probe.page.click("#btn-generate-archive")
    assert dl.value.suggested_filename.endswith(".csv")


def test_parquet_hidden_when_server_cannot_produce_it(probe):
    def fake(route):
        resp = route.fetch()
        body = resp.json()
        body["exports"] = {"parquet": False}
        route.fulfill(response=resp, json=body)
    probe.page.route("**/api/v1/health", fake)
    probe.goto("#/api")
    probe.page.wait_for_function("!document.querySelector('.export-fmt-btn[data-fmt=\"PARQUET\"]')")
    assert probe.page.locator(".export-fmt-btn").count() == 3


def test_region_buttons_not_duplicated_after_revisit(probe):
    probe.goto("#/api")
    probe.page.wait_for_selector(".export-reg-btn[data-reg='Lac']")
    first = probe.page.locator(".export-reg-btn").count()
    probe.goto("#/sectors")
    probe.goto("#/api")
    probe.page.wait_for_selector(".export-reg-btn[data-reg='Lac']")
    assert probe.page.locator(".export-reg-btn").count() == first


def test_truncated_export_warns_the_user(probe):
    def truncated(route):
        route.fulfill(status=200, body="id,sector\n1,health\n", content_type="text/csv", headers={
            "Content-Disposition": 'attachment; filename="x.csv"', "X-Export-Truncated": "true"})
    probe.page.route("**/api/v1/export/csv*", truncated)
    probe.goto("#/api")
    probe.page.wait_for_selector("#btn-generate-archive")
    probe.page.click('.export-fmt-btn[data-fmt="CSV"]')
    with probe.page.expect_download():
        probe.page.click("#btn-generate-archive")
    probe.page.wait_for_selector(".toast")
    assert "5" in probe.page.inner_text(".toast") and "000" in probe.page.inner_text(".toast")
