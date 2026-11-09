import pytest

from app.crops.engine import assess, load_crops, rank, trapezoid, verdict_for

MOUNDOU = {"rain_mm": 1100, "temp_mean_c": 27, "ph": 6.0}
ABECHE = {"rain_mm": 500, "temp_mean_c": 29, "ph": 7.0}
FAYA = {"rain_mm": 5, "temp_mean_c": 29, "ph": 8.0}


def test_trapezoid_shape():
    assert trapezoid(5, 0, 2, 8, 10) == 1.0
    assert trapezoid(1, 0, 2, 8, 10) == pytest.approx(0.5)
    assert trapezoid(9, 0, 2, 8, 10) == pytest.approx(0.5)
    assert trapezoid(0, 0, 2, 8, 10) == 0.0 and trapezoid(10, 0, 2, 8, 10) == 0.0


def test_known_cases():
    assert assess("cotton", MOUNDOU)["verdict"] in ("very_suitable", "suitable")
    assert assess("rice", FAYA)["verdict"] == "unsuitable"
    assert assess("millet", ABECHE)["verdict"] in ("very_suitable", "suitable")
    assert assess("cotton", ABECHE)["verdict"] == "unsuitable"


def test_limiting_factor_decides():
    r = assess("cotton", ABECHE)
    assert r["limiting"] == "rain_mm"
    assert r["score"] == r["factors"]["rain_mm"]["score"]


def test_missing_factor_is_reported_not_guessed():
    r = assess("millet", {"rain_mm": 500, "temp_mean_c": 29})
    assert r["unknown"] == ["ph"] and r["confidence"] == pytest.approx(0.67)
    assert assess("millet", {})["verdict"] == "unknown"


def test_unknown_crop_and_ranking():
    with pytest.raises(KeyError):
        assess("banana", MOUNDOU)
    ranked = rank(FAYA)
    assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)


def test_every_crop_is_well_formed_and_flagged():
    for cid, c in load_crops().items():
        for key in ("rain_mm", "temp_mean_c", "ph"):
            a, b, c2, d = c[key]
            assert a < b <= c2 < d, (cid, key)
        assert c["verified"] is True and c["source"] and c["ecoport_code"]


def test_verdict_thresholds():
    assert [verdict_for(s) for s in (0.9, 0.7, 0.5, 0.1)] == ["very_suitable", "suitable", "marginal", "unsuitable"]


LAI = {"rain_mm": 931, "temp_mean_c": 27.4, "ph": 6.3, "season_days": 184}


def test_rice_at_lai_is_unsuitable_rainfed_but_suitable_if_irrigated():
    r = assess("rice", LAI)
    assert r["verdict"] == "unsuitable" and r["limiting"] == "rain_mm"
    assert r["if_irrigated"]["verdict"] == "very_suitable" and r["if_irrigated"]["limiting"] != "rain_mm"


def test_irrigation_hint_only_when_water_is_the_limit():
    assert "if_irrigated" not in assess("cotton", {"rain_mm": 1100, "temp_mean_c": 27, "ph": 6.5, "season_days": 180})
    cold = assess("rice", {"rain_mm": 931, "temp_mean_c": 5, "ph": 6.3, "season_days": 184})
    assert "if_irrigated" not in cold   # cold is not a water problem: irrigation would not help
