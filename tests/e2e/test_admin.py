"""Patch A/B/C/D — admin UI: sign-in flow, dashboard, alerts, collections, quarantine review, audit journal.

The e2e server has no Supabase, so the browser is given a mocked config + auth endpoint
and mocked /api/v1/admin/* answers. The real backend rules are covered by tests/test_admin_auth.py.
"""

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

SECTORS = ["agriculture", "environment", "markets", "transport", "education", "economy", "health", "energy"]
COLLECTIONS = {
    "sector_ids": SECTORS, "job_running": False, "current_run": None, "next_run": None,
    "runs": [
        {"id": 3, "started_at": "2026-10-23T03:00:00", "trigger": "api", "triggered_by": None, "status": "partial",
         "sectors": SECTORS, "total_stored": 120,
         "results": {"health": {"stored": 0, "error": "<img src=x onerror=alert(1)> timeout"}, "energy": {"stored": 5, "errors": ["source 404"]}}},
        {"id": 2, "started_at": "2026-10-22T10:00:00", "trigger": "admin", "triggered_by": "me@x.org", "status": "completed",
         "sectors": ["health"], "total_stored": 7, "results": {"health": {"stored": 7}}},
        {"id": 1, "started_at": "2026-10-21T10:00:00", "trigger": "scheduler", "triggered_by": None, "status": "interrupted",
         "sectors": ["energy"], "total_stored": 0, "results": {}},
    ],
}


QITEMS = [
    {"id": 7, "status": "pending", "secteur": "health", "source_api": "World Bank", "date_reference": "2023-01-01",
     "indicateur": "<img src=x onerror=alert(1)> rate", "valeur": 140.0, "unite": "%", "region": "national",
     "flags": ["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"], "reviewed_by": None},
    {"id": 8, "status": "pending", "secteur": "agriculture", "source_api": "FAOSTAT", "date_reference": "2022-01-01",
     "indicateur": "Crop yield", "valeur": -5.0, "unite": "t/ha", "region": "Lac",
     "flags": ["NEGATIVE_ERROR", "SUPERVISOR_REVIEW"], "reviewed_by": None},
    {"id": 3, "status": "corrected", "secteur": "energy", "source_api": "World Bank", "date_reference": "2021-01-01",
     "indicateur": "Access to electricity", "valeur": 180.0, "unite": "%", "region": "national", "corrected_value": 18.0,
     "flags": ["DOMAIN_VIOLATION", "SUPERVISOR_REVIEW"], "reviewed_by": "boss@x.org", "reviewed_at": "2026-10-22T10:00:00",
     "review_note": "<b>typo</b>"},
]


DATA = [
    {"id": 41, "sector": "health", "indicator": "<img src=x onerror=alert(1)> Life expectancy", "value": 53.0, "unit": "years",
     "reference_date": "2023-01-01", "region": "national", "source": "World Bank", "approved_by": "FreeDatatd DS Engine"},
    {"id": 42, "sector": "agriculture", "indicator": "Crop yield", "value": 1.2, "unit": "t/ha",
     "reference_date": "2022-01-01", "region": "Lac", "source": "FAOSTAT", "approved_by": "boss@x.org"},
]
DELETED = [{"id": 5, "deleted_at": "2026-10-22T10:00:00", "deleted_by": "boss@x.org", "reason": "<b>bad sensor</b>",
            "row": {"sector": "energy", "indicator": "Access to electricity", "value": 180.0, "unit": "%",
                    "reference_date": "2021-01-01", "region": "national"}}]
REPORTS = [{"id": 9, "sector": "health", "model": "llama", "observations_used": 120, "created_at": "2026-10-20T10:00:00",
            "report": "<script>alert(1)</script> Findings"}]
TEAM = {"can_manage": True, "admins": [
    {"email": "me@x.org", "role": "owner", "permanent": True},
    {"email": "helper@x.org", "role": "admin", "permanent": False, "added_by": "me@x.org"},
    {"email": "<b>evil</b>@x.org", "role": "admin", "permanent": False, "added_by": "me@x.org"}]}


def _mock(page, *, me_status=200, overview=OVERVIEW, token_status=200, collections=None, run_reply=None,
          qitems=None, review_status=200, data=None, deleted=None, reports=None, team=None, mutate_status=200):
    page.route("**/api/v1/config", lambda r: r.fulfill(json={"admin": {"enabled": True, "supabase_url": SB, "anon_key": "anon"}}))

    def token(route):
        if token_status != 200:
            route.fulfill(status=token_status, json={"error_description": "Invalid login credentials"})
        else:
            route.fulfill(json={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600, "user": {"email": "me@x.org"}})
    page.route(f"{SB}/auth/v1/token*", token)

    class Calls(list):
        bodies: list

    calls = Calls()
    bodies = calls.bodies = []

    def admin(route):
        calls.append((route.request.method, route.request.url.split("/api/v1/admin")[1], route.request.headers.get("authorization")))
        path = route.request.url.split("/api/v1/admin")[1]
        if me_status != 200:
            route.fulfill(status=me_status, json={"detail": "nope"})
        elif path.startswith("/overview"):
            route.fulfill(json=overview)
        elif path.startswith("/collections/run"):
            bodies.append(route.request.post_data_json)
            route.fulfill(status=202, json=run_reply or {"status": "started"})
        elif path.startswith("/collections"):
            route.fulfill(json=collections if collections is not None else COLLECTIONS)
        elif route.request.method == "POST" and path.startswith(("/data/", "/reports/", "/admins")):
            bodies.append(route.request.post_data_json)
            route.fulfill(status=mutate_status, json={"status": "ok"} if mutate_status == 200 else {"detail": "gone"})
        elif path.startswith("/data/deleted"):
            route.fulfill(json={"items": DELETED if deleted is None else deleted})
        elif path.startswith("/data"):
            route.fulfill(json={"items": DATA if data is None else data})
        elif path.startswith("/reports"):
            route.fulfill(json={"items": REPORTS if reports is None else reports})
        elif path.startswith("/admins"):
            route.fulfill(json=TEAM if team is None else team)
        elif path.startswith("/quarantine/"):
            bodies.append(route.request.post_data_json)
            route.fulfill(status=review_status, json={"status": "ok"} if review_status == 200 else {"detail": "already reviewed"})
        elif path.startswith("/quarantine"):
            want = path.split("status=")[1].split("&")[0] if "status=" in path else "pending"
            qdata = QITEMS if qitems is None else qitems
            items = [i for i in qdata if want == "all" or i["status"] == want]
            counts = {st: len([i for i in qdata if i["status"] == st]) for st in ("pending", "approved", "corrected", "rejected")}
            route.fulfill(json={"items": items, "counts": counts})
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


def _open_collections(probe):
    _login(probe)
    probe.page.wait_for_selector(".admin-tab")
    probe.page.click('.admin-tab[data-tab="collections"]')


def test_collections_history_shows_status_trigger_and_errors_escaped(probe):
    _mock(probe.page)
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-runs-table")
    rows = probe.page.locator("#admin-runs-table tbody tr")
    assert rows.count() == 3
    assert [rows.nth(i).get_attribute("data-run-status") for i in range(3)] == ["partial", "completed", "interrupted"]
    first = rows.nth(0).inner_text()
    assert "<img src=x" in first and "source 404" in first            # failure reasons are visible...
    assert probe.page.locator("#admin-runs-table img").count() == 0   # ...and never interpreted as HTML
    assert "me@x.org" in rows.nth(1).inner_text()
    assert "{" not in probe.page.inner_text("#admin-runs-table")      # no raw i18n placeholders / keys
    assert "admin." not in probe.page.inner_text("#admin-runs-table")
    assert probe.page_errors == []


def test_run_selected_sends_only_the_ticked_sectors(probe):
    calls = _mock(probe.page)
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-run-sectors")
    probe.page.check('.admin-run-sector[value="transport"]')
    probe.page.check('.admin-run-sector[value="education"]')
    probe.page.click("#admin-run-selected")
    probe.page.wait_for_selector("#admin-runs-table")
    assert calls.bodies == [{"sectors": ["transport", "education"]}]


def test_run_all_sends_no_sector_filter(probe):
    calls = _mock(probe.page)
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-run-all")
    probe.page.click("#admin-run-all")
    probe.page.wait_for_selector("#admin-runs-table")
    assert calls.bodies == [{"sectors": None}]


def test_run_selected_without_a_tick_asks_to_pick_and_calls_nothing(probe):
    calls = _mock(probe.page)
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-run-selected")
    probe.page.click("#admin-run-selected")
    assert probe.page.inner_text("#admin-run-msg").strip() != ""
    assert calls.bodies == []


def test_buttons_are_disabled_while_a_harvest_runs(probe):
    running = dict(COLLECTIONS, job_running=True, current_run={"id": 9, "trigger": "admin", "sectors": ["health"], "started_at": "2026-10-23T10:00:00"})
    _mock(probe.page, collections=running)
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-run-state")
    assert probe.page.is_disabled("#admin-run-all") and probe.page.is_disabled("#admin-run-selected")
    assert "…" in probe.page.inner_text("#admin-run-state")


def test_empty_history_has_a_message(probe):
    _mock(probe.page, collections=dict(COLLECTIONS, runs=[]))
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-no-runs")
    assert probe.page.locator("#admin-runs-table").count() == 0


def test_already_running_reply_is_explained(probe):
    _mock(probe.page, run_reply={"status": "already_running"})
    _open_collections(probe)
    probe.page.wait_for_selector("#admin-run-all")
    probe.page.click("#admin-run-all")
    probe.page.wait_for_selector("#admin-runs-table")


# ── Patch C: quality / quarantine ───────────────────────────────────────────
def _open_quality(probe):
    _login(probe)
    probe.page.wait_for_selector(".admin-tab")
    probe.page.click('.admin-tab[data-tab="quality"]')
    probe.page.wait_for_selector("#admin-q-filters")


def test_quarantine_lists_pending_values_translated_and_escaped(probe):
    _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    rows = probe.page.locator("#admin-q-table tbody tr")
    assert rows.count() == 2 and rows.nth(0).get_attribute("data-q-status") == "pending"
    text = probe.page.inner_text("#admin-q-table")
    assert "<img src=x" in text                                          # hostile name shown as text...
    assert probe.page.locator("#admin-q-table img").count() == 0         # ...never interpreted as HTML
    assert "hors du domaine" in text.lower() and "140" in text and "-5" in text  # reason translated, values visible
    assert "admin." not in text and "DOMAIN_VIOLATION" not in text       # no raw keys or codes
    assert "(2)" in probe.page.inner_text("#admin-q-filters")            # pending counter


def test_approve_posts_to_the_right_row(probe):
    calls = _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('tr[data-q-id="8"] .admin-q-act[data-act="approve"]')
    probe.page.wait_for_selector("#admin-q-table")
    assert ("POST", "/quarantine/8/approve") in [(m, p) for m, p, _ in calls]
    assert [m for m, p, _ in calls if p.startswith("/quarantine?")] != []  # the list was reloaded


def test_reject_posts_to_the_right_row(probe):
    calls = _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('tr[data-q-id="7"] .admin-q-act[data-act="reject"]')
    probe.page.wait_for_selector("#admin-q-table")
    assert ("POST", "/quarantine/7/reject") in [(m, p) for m, p, _ in calls]


def test_correct_requires_a_number_then_sends_value_and_note(probe):
    calls = _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('tr[data-q-id="7"] .admin-q-act[data-act="correct"]')
    probe.page.click(".admin-q-confirm")                                  # empty value
    assert probe.page.inner_text("#admin-q-msg").strip() != "" and calls.bodies == []
    probe.page.fill(".admin-q-value", "14")
    probe.page.fill(".admin-q-note", "decimal slipped")
    probe.page.click(".admin-q-confirm")
    probe.page.wait_for_selector("#admin-q-table")
    assert calls.bodies == [{"value": 14, "note": "decimal slipped"}]
    assert ("POST", "/quarantine/7/correct") in [(m, p) for m, p, _ in calls]


def test_correct_can_be_cancelled_without_calling_anything(probe):
    calls = _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('tr[data-q-id="7"] .admin-q-act[data-act="correct"]')
    probe.page.click(".admin-q-cancel")
    probe.page.wait_for_selector('tr[data-q-id="7"] .admin-q-act[data-act="approve"]')
    assert calls.bodies == []


def test_value_already_handled_by_someone_else_refreshes_without_an_error_panel(probe):
    _mock(probe.page, review_status=409)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('tr[data-q-id="7"] .admin-q-act[data-act="approve"]')
    probe.page.wait_for_selector("#admin-q-table")
    assert probe.page.locator("#admin-retry").count() == 0
    assert "HTTP 409" not in probe.page.inner_text("#admin-panel")


def test_reviewed_values_show_decision_reviewer_and_published_value(probe):
    calls = _mock(probe.page)
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-table")
    probe.page.click('.admin-q-filter[data-status="corrected"]')
    probe.page.wait_for_selector('tr[data-q-id="3"]')
    assert any("status=corrected" in p for _, p, _ in calls)
    row = probe.page.inner_text('tr[data-q-id="3"]')
    assert "boss@x.org" in row and "18" in row and "180" in row
    assert "<b>typo</b>" in row and probe.page.locator('tr[data-q-id="3"] b').count() == 0
    assert probe.page.locator('tr[data-q-id="3"] .admin-q-act').count() == 0    # decided: no buttons


def test_empty_queue_says_nothing_to_review(probe):
    _mock(probe.page, qitems=[])
    _open_quality(probe)
    probe.page.wait_for_selector("#admin-q-empty")
    assert probe.page.locator("#admin-q-table").count() == 0


def test_quarantine_alert_on_the_overview_is_translated_with_its_number(probe):
    alert = {"level": "warning", "code": "quarantine_pending", "message": "x", "params": {"count": 12}}
    _mock(probe.page, overview=dict(OVERVIEW, alerts=[alert]))
    _login(probe)
    probe.page.wait_for_selector("#admin-sectors")
    text = probe.page.inner_text("#admin-panel")
    assert "12" in text and "{count}" not in text and "admin.alerts" not in text


# ── Patch D: data, reports, team ────────────────────────────────────────────
def _open(probe, tab, ready):
    _login(probe)
    probe.page.wait_for_selector(".admin-tab")
    probe.page.click(f'.admin-tab[data-tab="{tab}"]')
    probe.page.wait_for_selector(ready)


def _posts(calls):
    return [(m, p) for m, p, _ in calls if m == "POST"]


def test_data_tab_lists_values_escaped_with_archive(probe):
    _mock(probe.page)
    _open(probe, "data", "#admin-d-table")
    assert probe.page.locator("#admin-d-table tbody tr").count() == 2
    assert probe.page.locator("#admin-d-table img").count() == 0 and "<img src=x" in probe.page.inner_text("#admin-d-table")
    assert "boss@x.org" in probe.page.inner_text('tr[data-d-id="42"]')
    arch = probe.page.inner_text("#admin-d-deleted")
    assert "<b>bad sensor</b>" in arch and probe.page.locator("#admin-d-deleted b").count() == 0 and "boss@x.org" in arch
    assert "admin." not in probe.page.inner_text("#admin-panel") and "{who}" not in arch


def test_data_search_sends_filters(probe):
    calls = _mock(probe.page)
    _open(probe, "data", "#admin-d-form")
    probe.page.select_option("#admin-d-sector", "health")
    probe.page.fill("#admin-d-q", "life")
    probe.page.click("#admin-d-form button[type=submit]")
    probe.page.wait_for_selector("#admin-d-table")
    assert any("/data?" in p and "sector=health" in p and "q=life" in p for _, p, _ in calls)


def test_correct_needs_value_and_reason_then_posts(probe):
    calls = _mock(probe.page)
    _open(probe, "data", "#admin-d-table")
    probe.page.click('tr[data-d-id="42"] .admin-d-act[data-act="correct"]')
    probe.page.click(".admin-d-confirm")
    assert probe.page.inner_text("#admin-d-msg").strip() != "" and calls.bodies == []        # no reason
    probe.page.fill(".admin-d-reason", "typo in source")
    probe.page.click(".admin-d-confirm")
    assert calls.bodies == []                                                               # no value
    probe.page.fill(".admin-d-value", "12")
    probe.page.click(".admin-d-confirm")
    probe.page.wait_for_selector("#admin-d-table")
    assert calls.bodies == [{"value": 12, "reason": "typo in source"}]
    assert ("POST", "/data/42/correct") in _posts(calls)


def test_delete_needs_a_reason_and_can_be_cancelled(probe):
    calls = _mock(probe.page)
    _open(probe, "data", "#admin-d-table")
    probe.page.click('tr[data-d-id="41"] .admin-d-act[data-act="delete"]')
    probe.page.click(".admin-d-cancel")
    probe.page.wait_for_selector('tr[data-d-id="41"] .admin-d-act[data-act="delete"]')
    assert calls.bodies == []
    probe.page.click('tr[data-d-id="41"] .admin-d-act[data-act="delete"]')
    probe.page.click(".admin-d-confirm")
    assert calls.bodies == []
    probe.page.fill(".admin-d-reason", "duplicate")
    probe.page.click(".admin-d-confirm")
    probe.page.wait_for_selector("#admin-d-table")
    assert calls.bodies == [{"reason": "duplicate"}] and ("POST", "/data/41/delete") in _posts(calls)


def test_restore_posts_to_the_archive_entry(probe):
    calls = _mock(probe.page)
    _open(probe, "data", "#admin-d-deleted")
    probe.page.click(".admin-d-restore")
    probe.page.wait_for_selector("#admin-d-table")
    assert ("POST", "/data/deleted/5/restore") in _posts(calls)


def test_value_gone_meanwhile_refreshes_without_an_error_panel(probe):
    _mock(probe.page, mutate_status=404)
    _open(probe, "data", "#admin-d-table")
    probe.page.click('tr[data-d-id="41"] .admin-d-act[data-act="delete"]')
    probe.page.fill(".admin-d-reason", "duplicate")
    probe.page.click(".admin-d-confirm")
    probe.page.wait_for_selector("#admin-d-table")
    assert probe.page.locator("#admin-retry").count() == 0 and "HTTP 404" not in probe.page.inner_text("#admin-panel")


def test_empty_data_search_has_a_message(probe):
    _mock(probe.page, data=[], deleted=[])
    _open(probe, "data", "#admin-d-empty")
    assert probe.page.locator("#admin-d-nodeleted").count() == 1


def test_reports_escape_and_delete_with_reason(probe):
    calls = _mock(probe.page)
    _open(probe, "reports", ".admin-r-item")
    probe.page.click(".admin-r-item summary")
    assert "<script>alert(1)</script>" in probe.page.inner_text(".admin-r-item")
    probe.page.click(".admin-r-del")
    probe.page.click(".admin-r-confirm")
    assert calls.bodies == []
    probe.page.fill(".admin-r-reason", "wrong figures")
    probe.page.click(".admin-r-confirm")
    probe.page.wait_for_selector(".admin-r-item")
    assert calls.bodies == [{"reason": "wrong figures"}] and ("POST", "/reports/9/delete") in _posts(calls)


def test_no_reports_message(probe):
    _mock(probe.page, reports=[])
    _open(probe, "reports", "#admin-r-empty")


def test_team_owner_can_add_and_remove_but_not_remove_permanent_or_self(probe):
    calls = _mock(probe.page)
    _open(probe, "team", "#admin-team-table")
    assert probe.page.locator("#admin-team-table .admin-team-remove").count() == 2        # only the two non-permanent
    assert probe.page.locator('tr[data-email="me@x.org"] .admin-team-remove').count() == 0
    assert probe.page.locator("#admin-team-table b").count() == 0                         # hostile e-mail is text
    probe.page.fill("#admin-team-email", "not-an-email")
    probe.page.evaluate("document.getElementById('admin-team-form').dispatchEvent(new Event('submit', {cancelable: true}))")
    assert probe.page.inner_text("#admin-team-msg").strip() != "" and calls.bodies == []
    probe.page.fill("#admin-team-email", "New.Person@x.org")
    probe.page.click("#admin-team-form button[type=submit]")
    probe.page.wait_for_selector("#admin-team-table")
    assert calls.bodies == [{"email": "New.Person@x.org"}] and ("POST", "/admins") in _posts(calls)


def test_team_removal_asks_for_confirmation(probe):
    calls = _mock(probe.page)
    _open(probe, "team", "#admin-team-table")
    probe.page.once("dialog", lambda d: d.dismiss())
    probe.page.click('tr[data-email="helper@x.org"] .admin-team-remove')
    assert calls.bodies == []
    probe.page.once("dialog", lambda d: d.accept())
    probe.page.click('tr[data-email="helper@x.org"] .admin-team-remove')
    probe.page.wait_for_selector("#admin-team-table")
    assert calls.bodies == [{"email": "helper@x.org"}] and ("POST", "/admins/remove") in _posts(calls)


def test_non_owner_sees_the_team_but_no_controls(probe):
    _mock(probe.page, team=dict(TEAM, can_manage=False))
    _open(probe, "team", "#admin-team-readonly")
    assert probe.page.locator("#admin-team-form").count() == 0 and probe.page.locator(".admin-team-remove").count() == 0
