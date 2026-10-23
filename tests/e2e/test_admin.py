"""Patch A — admin UI: sign-in flow, dashboard, alerts, audit journal, error handling.

The e2e server has no Supabase, so the browser is given a mocked config + auth endpoint
and mocked /api/v1/admin/* answers. The real backend rules are covered by tests/test_admin_auth.py.
"""
import json

SB = "https://sb.test"
OVERVIEW = {
    "generated_at": "2026-10-23T10:00:00+00:00", "health": "critical",
    "service": {"storage_backend": "supabase", "scheduler": {"last_run": None}},
    "data": {"total": 11968, "last_update": "2026-09-13T12:06:42", "regions_covered": 21,
             "sectors": [{"id": "agriculture", "count": 2932, "last_published": "2026-09-13T12:06:42"},
                         {"id": "health", "count": 0, "last_published": None}]},
    "quality": {"score_global": 0.97, "anomalies": 4, "total_raw": 844, "total_clean": 11968, "total_public": 11968},
    "alerts": [
        {"level": "critical", "code": "collection_stalled", "message": "x", "params": {"days": 40}},
        {"level": "warning", "code": "sector_empty", "message": "x", "params": {"sector": "health"}},
        {"level": "info", "code": "totally_new_code", "message": "Server side English text", "params": {}},
    ],
}


def _mock(page, *, me_status=200, overview=OVERVIEW, token_status=200):
    page.route("**/api/v1/config", lambda r: r.fulfill(json={"admin": {"enabled": True, "supabase_url": SB, "anon_key": "anon"}}))

    def token(route):
        if token_status != 200:
            route.fulfill(status=token_status, json={"error_description": "Invalid login credentials"})
        else:
            route.fulfill(json={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600, "user": {"email": "me@x.org"}})
    page.route(f"{SB}/auth/v1/token*", token)

    calls = []

    def admin(route):
        calls.append((route.request.method, route.request.url.split("/api/v1/admin")[1], route.request.headers.get("authorization")))
        path = route.request.url.split("/api/v1/admin")[1]
        if me_status != 200:
            route.fulfill(status=me_status, json={"detail": "nope"})
        elif path.startswith("/overview"):
            route.fulfill(json=overview)
        elif path.startswith("/audit-log"):
            route.fulfill(json={"entries": [{"created_at": "2026-10-23T09:00:00", "admin_email": "me@x.org", "action": "login", "target": None, "detail": {}},
                                            {"created_at": "2026-10-23T09:05:00", "admin_email": "<img src=x onerror=alert(1)>", "action": "weird.action", "target": "<b>t</b>", "detail": {}}]})
        else:
            route.fulfill(json={"email": "me@x.org", "role": "owner"})
    page.route("**/api/v1/admin/**", admin)
    return calls


def _login(probe):
    probe.goto("#/admin")
    probe.page.wait_for_selector("#admin-login-form")
    probe.page.fill("#admin-email", "me@x.org")
    probe.page.fill("#admin-password", "secret")
    probe.page.click("#admin-login-btn")


def test_unconfigured_server_says_so_and_offers_no_login(probe):
    probe.goto("#/admin")
    probe.page.wait_for_selector("#admin-disabled")
    assert probe.page.locator("#admin-login-form").count() == 0


def test_signed_out_visitor_sees_only_the_login_form_and_no_data(probe):
    _mock(probe.page)
    probe.goto("#/admin")
    probe.page.wait_for_selector("#admin-login-form")
    assert probe.page.locator("#admin-health-banner").count() == 0


def test_login_success_shows_dashboard_and_sends_bearer_token(probe):
    calls = _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector("#admin-health-banner")
    assert any(m == "POST" and p == "/session" and a == "Bearer tok" for m, p, a in calls)   # login recorded
    assert any(p == "/overview" and a == "Bearer tok" for _, p, a in calls)
    assert "11" in probe.page.inner_text("#admin-kpi-total") and "968" in probe.page.inner_text("#admin-kpi-total")
    assert probe.page.inner_text("#admin-kpi-score") == "97.0%"
    assert probe.page.get_attribute("#admin-health-banner", "data-health") == "critical"


def test_alerts_are_translated_with_their_numbers_and_sorted_by_server(probe):
    _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector(".admin-alert")
    texts = probe.page.locator(".admin-alert").all_inner_texts()
    assert "40" in texts[0] and probe.page.locator(".admin-alert").first.get_attribute("data-level") == "critical"
    assert "{days}" not in " ".join(texts) and "{sector}" not in " ".join(texts)
    assert "Server side English text" in texts[2]                       # unknown code falls back to the server text


def test_sector_states_are_flagged(probe):
    _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector("#admin-sectors")
    assert probe.page.get_attribute('#admin-sectors tr[data-sector="health"]', "data-state") == "empty"
    assert probe.page.get_attribute('#admin-sectors tr[data-sector="agriculture"]', "data-state") == "late"
    assert probe.page.get_attribute('#admin-sectors tr[data-sector="markets"]', "data-state") == "unknown"   # absent from payload


def test_wrong_password_shows_message_and_stays_on_login(probe):
    _mock(probe.page, token_status=400)
    _login(probe)
    probe.page.wait_for_selector("#admin-login-error")
    assert probe.page.locator("#admin-health-banner").count() == 0
    assert probe.page.is_visible("#admin-login-form")


def test_signed_in_but_not_admin_is_refused_and_signed_out(probe):
    _mock(probe.page, me_status=403)
    _login(probe)
    probe.page.wait_for_selector("#admin-login-error")
    assert probe.page.locator("#admin-health-banner").count() == 0
    assert probe.page.evaluate("sessionStorage.getItem('fd_admin_session')") is None


def test_sign_out_clears_the_session(probe):
    _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector("#admin-signout")
    probe.page.click("#admin-signout")
    probe.page.wait_for_selector("#admin-login-form")
    assert probe.page.evaluate("sessionStorage.getItem('fd_admin_session')") is None


def test_audit_journal_escapes_hostile_values(probe):
    _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector(".admin-tab")
    probe.page.click('.admin-tab[data-tab="audit"]')
    probe.page.wait_for_selector("#admin-audit-table")
    assert probe.page.locator("#admin-audit-table img").count() == 0    # not interpreted as HTML
    assert "<img src=x" in probe.page.inner_text("#admin-audit-table")
    assert probe.page.locator("#admin-audit-table tbody tr").count() == 2
    assert probe.page_errors == []


def test_expired_session_on_reload_goes_back_to_login(probe):
    _mock(probe.page)
    _login(probe)
    probe.page.wait_for_selector("#admin-health-banner")
    probe.page.unroute("**/api/v1/admin/**")
    probe.page.route("**/api/v1/admin/**", lambda r: r.fulfill(status=401, json={"detail": "expired"}))
    probe.page.route(f"{SB}/auth/v1/token*", lambda r: r.fulfill(status=400, json={"msg": "refresh revoked"}))
    probe.page.click("#admin-refresh")
    probe.page.wait_for_selector("#admin-login-form")
