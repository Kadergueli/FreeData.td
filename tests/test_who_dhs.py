"""WHO GHO and DHS Program: parsing of the real answer shapes (seen live in Nov 2026) and the collectors."""
import asyncio
from datetime import UTC, datetime

import pytest

from app.agents import HealthAgent
from app.agents.base import BaseAgent
from app.agents.dhs import clean_region, parse_dhs
from app.agents.who_gho import GHO_INDICATORS, parse_gho
from app.services.storage import ObservationRepository

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def _gho(year, value, dim1="SEX_BTSX", src=None, date="2026-10-01T16:11:13+02:00", **extra):
    return {"TimeDim": year, "NumericValue": value, "Dim1": dim1, "Dim2": None, "Dim3": None,
            "DataSourceDim": src, "Date": date, **extra}


def test_gho_keeps_the_all_population_row_one_per_year():
    payload = {"value": [
        _gho(2022, 59.2), _gho(2022, 57.0, dim1="SEX_FMLE"), _gho(2022, 61.0, dim1="SEX_MLE"),
        _gho(2021, 58.0), _gho(2023, None), _gho(2020, 55.5, dim2="X") if False else {**_gho(2020, 1.0), "Dim2": "AGE_5"},
    ]}
    rows = parse_gho(payload, "WHOSIS_000001", NOW)
    assert [(r["year"], r["value"]) for r in rows] == [(2021, 58.0), (2022, 59.2)]
    assert rows[0]["source"] == "WHO GHO" and rows[0]["region"] == "national" and rows[0]["unit"] == "years"


def test_gho_prefers_the_who_estimate_then_the_newest_update_and_drops_projections():
    payload = {"value": [
        _gho(2019, 10.0, src="DHS 2019", date="2026-10-01"),
        _gho(2019, 11.0, src=None, date="2025-01-01"),
        _gho(2019, 12.0, src=None, date="2026-02-01"),
        _gho(2030, 9.0),                                   # projection
    ]}
    rows = parse_gho(payload, "WHOSIS_000001", NOW)
    assert [(r["year"], r["value"]) for r in rows] == [(2019, 12.0)]


@pytest.mark.parametrize("bad", [None, [], {}, {"value": "x"}, {"value": [None, 3]}])
def test_gho_unexpected_shapes_give_nothing(bad):
    assert parse_gho(bad, "WHOSIS_000001", NOW) == []
    assert parse_gho({"value": [_gho(2020, 1.0)]}, "NOT_A_CODE", NOW) == []


def test_gho_table_is_clean():
    for code, (name, unit) in GHO_INDICATORS.items():
        assert name and len(unit) <= 40, code
    assert len({n.lower() for n, _ in GHO_INDICATORS.values()}) == len(GHO_INDICATORS)


def _dhs(ind="CM_ECMR_C_U5M", value=194, year=1997, cat="Region", label="N'Djaména 1997", by=0, pref=1, name="Under-five mortality rate"):
    return {"IndicatorId": ind, "Indicator": name, "Value": value, "SurveyYear": year, "CharacteristicCategory": cat,
            "CharacteristicLabel": label, "ByVariableId": by, "IsPreferred": pref, "IsTotal": 1 if cat == "Total" else 0}


def test_dhs_regions_national_and_breakdowns():
    payload = {"TotalPages": 1, "Data": [
        _dhs(), _dhs(cat="Total", label="Total", value=191), _dhs(by=15, value=1),          # by another variable: dropped
        _dhs(ind="UNKNOWN_ID"), _dhs(value=""), _dhs(cat="Urban", label="Urban"),
        _dhs(value=150, year=2014, label="Logone Occidental 2014"),
    ]}
    rows = parse_dhs(payload)
    got = {(r["year"], r["region"]): r["value"] for r in rows}
    assert got == {(1997, "N'Djamena"): 194.0, (1997, "national"): 191.0, (2014, "Logone Occidental"): 150.0}
    assert all(r["source"] == "DHS Program" and r["unit"] == "per 1,000 live births" for r in rows)


def test_dhs_preferred_row_wins_a_duplicate():
    rows = parse_dhs({"Data": [_dhs(value=1, pref=0), _dhs(value=2, pref=1)]})
    assert [r["value"] for r in rows] == [2.0]


@pytest.mark.parametrize("label,expected", [("N'Djaména 1997", "N'Djamena"), ("Mayo-Kebbi Est 2014", "Mayo-Kebbi Est"),
                                            ("Ouaddaï (2004)", "Ouaddai"), ("Guéra", "Guera"), ("", "national")])
def test_dhs_region_names_match_the_stored_ones(label, expected):
    assert clean_region(label) == expected


def test_health_collects_who_and_dhs_and_stores_them_with_their_own_terms(monkeypatch, tmp_path):
    async def fake_fetch(client, url, params=None, **kw):
        if "ghoapi" in url:
            return {"value": [_gho(2022, 59.2)]}
        return {"TotalPages": 1, "Data": [_dhs(), _dhs(cat="Total", label="Total", value=191)]}
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    repo = ObservationRepository(database_path=tmp_path / "h.db")
    agent = HealthAgent(repo)
    assert asyncio.run(agent.run("who-gho")).stored >= 1
    assert asyncio.run(HealthAgent(repo).run("dhs")).stored == 4      # national call + regional call, same fake answer
    rows = repo.list_observations(sector="health", limit=500)
    licences = {r["source"]: r["license"] for r in rows}
    assert licences["WHO GHO"].startswith("CC BY-NC-SA") and licences["DHS Program"] == "DHS Program terms of use"


def test_who_gho_with_no_answer_fails_loudly(monkeypatch, tmp_path):
    async def nothing(client, url, params=None, **kw):
        return None
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(nothing))
    with pytest.raises(RuntimeError, match="WHO GHO returned nothing"):
        asyncio.run(HealthAgent(ObservationRepository(database_path=tmp_path / "h.db"))._collect_who_gho())


def test_gho_accepts_a_second_breakdown_when_no_clean_row_exists():
    rows = [{**_gho(2020, 10.0), "Dim2": "AGEGROUP_YEARS18-PLUS"}, {**_gho(2020, 11.0, dim1="SEX_FMLE"), "Dim2": "AGEGROUP_YEARS18-PLUS"}]
    got = parse_gho({"value": rows}, "WHOSIS_000001", NOW)
    assert [(r["year"], r["value"]) for r in got] == [(2020, 10.0)]


def test_gho_describes_why_a_series_is_empty():
    from app.agents.who_gho import describe_rows
    assert describe_rows({"value": []}) == "no data for Chad"
    text = describe_rows({"value": [{"Dim1": "X", "Dim2": "Y", "Dim3": None, "NumericValue": None}]})
    assert "1 rows but none usable" in text and "'X'" in text


def test_gho_ignores_years_before_the_platform_starts():
    rows = parse_gho({"value": [_gho(1944, 300.0), _gho(1959, 280.0), _gho(1960, 270.0), _gho(2020, 114.0)]}, "MDG_0000000007", NOW)
    assert [r["year"] for r in rows] == [1960, 2020]
