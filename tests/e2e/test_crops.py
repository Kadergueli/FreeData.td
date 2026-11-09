"""Crop suitability page, with the API answered by a mock (no climate or soil file needed)."""
from __future__ import annotations


CATALOGUE = {"crops": [{"id": "millet", "name_fr": "Mil", "name_en": "Pearl millet", "scientific_name": "Pennisetum glaucum"},
                       {"id": "cotton", "name_fr": "Coton", "name_en": "Cotton", "scientific_name": "Gossypium hirsutum"}],
             "regions": ["Abéché (Ouaddaï)", "Moundou (Logone Occidental)"]}
SITE = {"rain_mm": 357.0, "temp_mean_c": 27.93, "season_days": 92, "annual_rain_mm": 400.1, "wet_months": ["JUL", "AUG", "SEP"], "ph": 7.47}
REQ = {"rain_mm": [200, 400, 900, 1700], "temp_mean_c": [12, 25, 35, 40], "ph": [4.5, 5, 6.5, 8.3], "cycle_days": [60, 120]}


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
        if "crop=millet" in url:
            data = [_result("millet", "Mil", 0.62, "suitable", "rain_mm")]
        else:
            data = [_result("millet", "Mil", 0.62, "suitable", "rain_mm"), _result("cotton", "Coton", 0.0, "unsuitable", "rain_mm")]
        route.fulfill(json={"region": "Abéché (Ouaddaï)", "site": SITE, "missing": [], "results": data})
    page.route("**/api/v1/crops/suitability*", suit)


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
