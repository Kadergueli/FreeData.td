"""Crop suitability page, with the API answered by a mock (no climate or soil file needed)."""
from __future__ import annotations


CATALOGUE = {"crops": [{"id": "millet", "name_fr": "Mil", "name_en": "Pearl millet", "scientific_name": "Pennisetum glaucum"},
                       {"id": "cotton", "name_fr": "Coton", "name_en": "Cotton", "scientific_name": "Gossypium hirsutum"},
                       {"id": "rice", "name_fr": "Riz", "name_en": "Rice", "scientific_name": "Oryza sativa"}],
             "regions": ["Abéché (Ouaddaï)", "Moundou (Logone Occidental)"]}
SITE = {"rain_mm": 357.0, "temp_mean_c": 27.93, "season_days": 92, "annual_rain_mm": 400.1, "wet_months": ["JUL", "AUG", "SEP"], "ph": 7.47}
REQ = {"rain_mm": [200, 400, 900, 1700], "temp_mean_c": [12, 25, 35, 40], "ph": [4.5, 5, 6.5, 8.3], "cycle_days": [60, 120]}


CALENDAR = [{"month": m, "score": 1.0 if m == 7 else (0.5 if m in (6, 8) else 0.0),
             "verdict": "suitable" if m == 7 else ("marginal" if m in (6, 8) else "unsuitable"), "cycle_end": m + 2} for m in range(1, 13)]


def _result(crop, name, score, verdict, limiting):
    return {"crop": crop, "name_fr": name, "name_en": name, "score": score, "verdict": verdict, "limiting": limiting,
            "requirements": REQ, "factors": {"rain_mm": {"value": 357.0, "score": 0.785}, "temp_mean_c": {"value": 27.93, "score": 1.0},
                                              "season_days": {"value": 92, "score": 1.0}, "ph": {"value": 7.47, "score": 0.46}}}


def _mock(page, calls):
    page.route("**/api/v1/crops", lambda r: r.fulfill(json=CATALOGUE))

    def suit(route):
        url = route.request.url
        calls.append(url)
        if "region=Atlantis" in url:
            return route.fulfill(status=404, json={"detail": "Unknown region 'Atlantis'"})
        if "crop=rice" in url:
            rice = _result("rice", "Riz", 0.0, "unsuitable", "rain_mm")
            rice["if_irrigated"] = {"score": 1.0, "verdict": "very_suitable", "limiting": "temp_mean_c"}
            data = [rice]
        elif "crop=millet" in url:
            lang = "en" if "lang=en" in url else "fr"
            summary = "Pearl millet in Abéché: suitable (62%)." if lang == "en" else "Mil à Abéché : verdict adapté (62 %)."
            return route.fulfill(json={"region": "Abéché (Ouaddaï)", "site": SITE, "missing": [], "calendar": CALENDAR,
                                       "summary": summary, "results": [_result("millet", "Mil", 0.62, "suitable", "rain_mm")]})
        else:
            data = [_result("millet", "Mil", 0.62, "suitable", "rain_mm"), _result("cotton", "Coton", 0.0, "unsuitable", "rain_mm")]
        route.fulfill(json={"region": "Abéché (Ouaddaï)", "site": SITE, "missing": [], "results": data})
    page.route("**/api/v1/crops/suitability*", suit)

    def explain(route):
        calls.append(route.request.method + " " + route.request.url)
        mode = route.request.url
        if "crop=cotton" in mode:   # the AI is unavailable for this one: the rule-based text comes back
            return route.fulfill(json={"text": "Texte par règles.", "source": "template", "model": None, "reason": "no-key", "lang": "fr"})
        route.fulfill(json={"text": "Note rédigée par IA.", "source": "ai", "model": "m", "lang": "fr"})
    page.route("**/api/v1/crops/explain*", explain)

    def cmap(route):
        calls.append(route.request.url)
        route.fulfill(json={"crop": "millet", "name_fr": "Mil", "name_en": "Pearl millet", "regions": [
            {"region": "Abéché (Ouaddaï)", "lat": 13.82, "lon": 20.83, "score": 0.62, "verdict": "suitable", "limiting": "rain_mm", "if_irrigated": 0.78},
            {"region": "Moundou (Logone Occidental)", "lat": 8.56, "lon": 16.08, "score": 0.95, "verdict": "very_suitable", "limiting": None, "if_irrigated": None}]})
    page.route("**/api/v1/crops/map*", cmap)


def test_ranking_then_detail_and_url_keeps_the_choice(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.goto("#/crops")
    probe.page.wait_for_selector(".crop-rank-row")
    assert probe.page.locator(".crop-rank-row").count() == 2
    assert "Mil" in probe.page.inner_text(".crop-rank-row >> nth=0")
    probe.page.click('.crop-rank-row[data-crop="millet"]')
    probe.page.wait_for_selector(".crop-factors")
    text = probe.page.inner_text("#crop-result")
    assert "Adaptée" in text and "62 %" in text and "Pluie de la saison" in text
    assert "facteur limitant" in text.lower()          # the badge is upper-cased by the stylesheet
    assert "Optimum 400–900 mm" in text and "3 mois" in text
    assert probe.page.locator(".crop-factor.is-limiting").count() == 1
    assert "crop=millet" in probe.page.evaluate("location.hash")
    assert probe.page_errors == []


def test_deep_link_and_error_message(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector(".crop-factors")
    assert probe.page.input_value("#crop-crop") == "millet"
    probe.page.route("**/api/v1/crops/suitability*", lambda r: r.fulfill(status=404, json={"detail": "Unknown region 'x'"}))
    probe.page.select_option("#crop-region", "Moundou (Logone Occidental)")
    probe.page.wait_for_selector("#crop-output .alert--danger")
    assert "Calcul impossible" in probe.page.inner_text("#crop-output")


def test_no_data_says_so(probe):
    probe.page.route("**/api/v1/crops", lambda r: r.fulfill(json={"crops": [], "regions": []}))
    probe.goto("#/crops")
    probe.page.wait_for_selector("#crop-output .alert--danger")
    assert "pas encore chargées" in probe.page.inner_text("#crop-output")


def test_phone_width_has_no_horizontal_scroll(probe):
    _mock(probe.page, [])
    probe.page.set_viewport_size({"width": 390, "height": 800})
    probe.goto("#/crops")
    probe.page.wait_for_selector(".crop-rank-row")
    assert probe.page.evaluate("document.documentElement.scrollWidth <= 390")


def test_irrigated_option_is_shown_when_rain_is_the_limit(probe):
    _mock(probe.page, [])
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=rice")
    probe.page.wait_for_selector("#crop-irrigated")
    text = probe.page.inner_text("#crop-irrigated")
    assert "100 %" in text and "irrigation" in text.lower()
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector("#crop-result")
    assert probe.page.locator("#crop-irrigated").count() == 0
    assert probe.page_errors == []


def test_calendar_summary_and_ai_note(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector(".crop-cal")
    assert probe.page.locator(".crop-cal-cell").count() == 12
    assert probe.page.locator(".crop-cal-cell--good").count() == 1 and probe.page.locator(".crop-cal-cell--maybe").count() == 2
    july = probe.page.get_attribute(".crop-cal-cell >> nth=6", "aria-label")
    assert "juillet" in july and "favorable" in july
    assert "verdict adapté" in probe.page.inner_text("#crop-summary-text")
    probe.page.click("#crop-ai-btn")
    probe.page.wait_for_selector("#crop-ai-out .crop-ai-note")
    note = probe.page.inner_text("#crop-ai-out")
    assert "Note rédigée par IA." in note and "Aucun chiffre ajouté" in note
    assert probe.page.locator("#crop-ai-out .is-ai").count() == 1
    assert any(c.startswith("POST ") and "lang=fr" in c and "crop=millet" in c for c in calls)
    assert probe.page_errors == []


def test_ai_fallback_is_labelled_and_errors_are_kept_local(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector("#crop-ai-btn")
    probe.page.route("**/api/v1/crops/explain*", lambda r: r.fulfill(
        json={"text": "Texte par règles.", "source": "template", "model": None, "reason": "rate-limited", "lang": "fr"}))
    probe.page.click("#crop-ai-btn")
    probe.page.wait_for_selector("#crop-ai-out .crop-ai-note")
    assert "limite" in probe.page.inner_text("#crop-ai-out") and probe.page.locator("#crop-ai-out .is-ai").count() == 0
    probe.page.route("**/api/v1/crops/explain*", lambda r: r.fulfill(status=500, json={"detail": "boom"}))
    probe.page.click("#crop-ai-btn")
    probe.page.wait_for_selector("#crop-ai-out .alert--danger")
    assert "reste valable" in probe.page.inner_text("#crop-ai-out")
    assert probe.page.is_enabled("#crop-ai-btn") and "verdict adapté" in probe.page.inner_text("#crop-summary-text")


def test_calendar_and_ai_follow_the_interface_language(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.page.add_init_script("localStorage.setItem('fd_lang', 'en')")
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector(".crop-cal")
    assert "Rainfed sowing calendar" in probe.page.inner_text(".crop-calendar")
    assert "favourable sowing" in probe.page.inner_text(".crop-cal-legend")
    assert "July" in probe.page.get_attribute(".crop-cal-cell >> nth=6", "aria-label")
    assert "Pearl millet in Abéché: suitable (62%)." in probe.page.inner_text("#crop-summary-text")
    assert probe.page.inner_text("#crop-ai-btn") == "Write a note with AI"
    assert any("lang=en" in c for c in calls)


def test_map_shows_one_dot_per_region_and_a_click_selects_the_region(probe):
    calls: list[str] = []
    _mock(probe.page, calls)
    probe.goto("#/crops?region=Abéché (Ouaddaï)&crop=millet")
    probe.page.wait_for_selector(".crop-map-dot")
    assert probe.page.locator(".crop-map-dot").count() == 2
    assert probe.page.locator(".crop-map-dot.is-selected").get_attribute("data-region") == "Abéché (Ouaddaï)"
    assert "irrigué" in probe.page.locator(".crop-map-dot >> nth=0").get_attribute("aria-label")
    assert any("/crops/map" in c and "crop=millet" in c for c in calls)
    probe.page.locator(".crop-map-dot >> nth=1").dispatch_event("click")
    probe.page.wait_for_function("document.getElementById('crop-region').value.startsWith(\"Moundou\")")
    assert probe.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_no_map_in_the_ranking_view(probe):
    _mock(probe.page, [])
    probe.goto("#/crops")
    probe.page.wait_for_selector(".crop-rank-row")
    assert probe.page.locator("#crop-map").count() == 0
