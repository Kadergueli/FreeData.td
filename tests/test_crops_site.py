import json

import pytest
from fastapi.testclient import TestClient

from app.crops import sites
from app.crops.engine import assess
from app.crops.profile import MONTHS, build_profile

ABECHE_RAIN = dict(zip(MONTHS, [0, 0, 0, .03, .28, .83, 3.43, 5.84, 2.32, .28, 0, 0]))   # NASA POWER, probe of Nov 2026
ABECHE_TEMP = dict(zip(MONTHS, [23.5, 26.89, 29.82, 32.39, 33.46, 32.49, 29.46, 26.79, 27.53, 28.12, 26.03, 23.77]))
SUD_RAIN = dict(zip(MONTHS, [0, 0, .3, 1.5, 3.2, 4.3, 5.5, 6.5, 5.5, 3.0, .2, 0]))
SUD_TEMP = dict(zip(MONTHS, [26, 28, 30, 29, 27, 26, 25, 25, 25, 26, 26, 25]))
FAYA_RAIN = dict(zip(MONTHS, [0] * 12))
FAYA_TEMP = dict(zip(MONTHS, [18, 21, 25, 29, 32, 34, 34, 33, 33, 30, 24, 19]))


def test_profile_uses_the_rainy_season_only():
    p = build_profile(ABECHE_RAIN, ABECHE_TEMP)
    assert p["wet_months"] == ["JUL", "AUG", "SEP"] and p["season_days"] == 92
    assert p["rain_mm"] == pytest.approx(357, abs=1) and p["annual_rain_mm"] == pytest.approx(400, abs=1)
    assert p["temp_mean_c"] == pytest.approx((29.46 + 26.79 + 27.53) / 3, abs=0.01)


def test_profile_of_a_desert_has_no_season():
    p = build_profile(FAYA_RAIN, FAYA_TEMP)
    assert p["wet_months"] == [] and p["season_days"] == 0 and p["rain_mm"] == 0


def test_season_length_limits_a_long_cycle_crop():
    short = assess("cassava", {"rain_mm": 1200, "temp_mean_c": 27, "ph": 6.0, "season_days": 60})
    assert short["limiting"] == "season_days" and short["factors"]["season_days"]["score"] < 0.4
    full = assess("cassava", {"rain_mm": 1200, "temp_mean_c": 27, "ph": 6.0, "season_days": 365})
    assert full["factors"]["season_days"]["score"] == 1.0 and full["confidence"] == 1.0
    assert "season_days" not in assess("cassava", {"rain_mm": 1200, "temp_mean_c": 27, "ph": 6.0})["factors"]


@pytest.fixture
def data(tmp_path, monkeypatch):
    clim = {"regions": {
        "Abéché (Ouaddaï)": {"rain_mm_day": ABECHE_RAIN, "temp_c": ABECHE_TEMP},
        "Moundou (Logone Occidental)": {"rain_mm_day": SUD_RAIN, "temp_c": SUD_TEMP},
        "Faya-Largeau (Borkou)": {"rain_mm_day": FAYA_RAIN, "temp_c": FAYA_TEMP}}}
    soil = {"regions": {"Abéché (Ouaddaï)": {"ph": 7.47}, "Moundou (Logone Occidental)": {"ph": 6.08},
                        "Faya-Largeau (Borkou)": {"ph": 8.13}}}
    (tmp_path / "c.json").write_text(json.dumps(clim), encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps(soil), encoding="utf-8")
    monkeypatch.setattr(sites, "CLIMATE_FILE", tmp_path / "c.json")
    monkeypatch.setattr(sites, "SOILS_FILE", tmp_path / "s.json")
    sites.load_climate.cache_clear(); sites.load_soils.cache_clear()
    yield
    sites.load_climate.cache_clear(); sites.load_soils.cache_clear()


def test_find_region_ignores_accents_and_case(data):
    assert sites.find_region("abeche") == "Abéché (Ouaddaï)"
    assert sites.find_region("OUADDAI") == "Abéché (Ouaddaï)"
    assert sites.find_region("moundou") == "Moundou (Logone Occidental)"
    assert sites.find_region("atlantis") is None and sites.find_region("  ") is None


def test_site_for_reports_what_is_missing(data, monkeypatch):
    full = sites.site_for("Abéché (Ouaddaï)")
    assert full["missing"] == [] and full["site"]["ph"] == 7.47 and full["site"]["season_days"] == 92
    monkeypatch.setattr(sites, "SOILS_FILE", sites.HERE / "absent.json")
    sites.load_soils.cache_clear()
    assert sites.site_for("Abéché (Ouaddaï)")["missing"] == ["soil"]


def test_soil_ph_lowers_the_score_without_blocking(data):
    base = {"rain_mm": 357, "temp_mean_c": 27.9, "season_days": 92}
    good = assess("millet", {**base, "ph": 6.0})
    alkaline = assess("millet", {**base, "ph": 7.47})
    awful = assess("millet", {**base, "ph": 12})
    assert good["score"] == good["climate_score"]
    assert awful["score"] == pytest.approx(awful["climate_score"] * 0.6, abs=0.001)   # at most 40 % off
    assert awful["score"] < alkaline["score"] < good["score"] and alkaline["limiting"] == "rain_mm"
    assert assess("millet", {"ph": 6.0})["verdict"] == "unknown"                       # soil alone cannot decide


def test_api_known_cases(data):
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/v1/crops/suitability", params={"region": "moundou", "crop": "cotton"})
    assert r.status_code == 200 and r.json()["results"][0]["verdict"] in ("very_suitable", "suitable")
    r = client.get("/api/v1/crops/suitability", params={"region": "abeche", "crop": "millet"})
    assert r.json()["results"][0]["verdict"] in ("very_suitable", "suitable")
    assert r.json()["results"][0]["name_fr"] == "Mil"
    r = client.get("/api/v1/crops/suitability", params={"region": "faya", "crop": "rice"})
    assert r.json()["results"][0]["verdict"] == "unsuitable"


def test_api_ranks_all_crops_and_rejects_bad_input(data):
    from app.main import app
    client = TestClient(app)
    ranked = client.get("/api/v1/crops/suitability", params={"region": "moundou"}).json()["results"]
    assert len(ranked) == 9 and [x["score"] for x in ranked] == sorted((x["score"] for x in ranked), reverse=True)
    assert client.get("/api/v1/crops/suitability", params={"region": "atlantis"}).status_code == 404
    assert client.get("/api/v1/crops/suitability", params={"region": "moundou", "crop": "banana"}).status_code == 404
    listing = client.get("/api/v1/crops").json()
    assert len(listing["crops"]) == 9 and "Abéché (Ouaddaï)" in listing["regions"]


def test_api_without_data_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(sites, "CLIMATE_FILE", tmp_path / "none.json"); monkeypatch.setattr(sites, "SOILS_FILE", tmp_path / "none2.json")
    sites.load_climate.cache_clear(); sites.load_soils.cache_clear()
    from app.main import app
    assert TestClient(app).get("/api/v1/crops/suitability", params={"region": "moundou"}).status_code == 404
    sites.load_climate.cache_clear(); sites.load_soils.cache_clear()
