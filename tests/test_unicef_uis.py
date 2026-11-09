import asyncio

from app.services.storage import ObservationRepository

import httpx

from app.agents import education as edu
from app.agents.education import EducationAgent
from app.agents.unesco_uis import describe_uis, parse_uis
from app.agents.unicef import is_total, parse_unicef

HEADER = "REF_AREA,Geographic area,INDICATOR,Indicator,SEX,Sex,WEALTH_QUINTILE,Wealth Quintile,RESIDENCE,Residence,UNIT_MEASURE,Unit of measure,TIME_PERIOD,OBS_VALUE"
CSV = "\n".join([
    HEADER,
    "TCD,Chad,ED_CR_L1,Completion rate primary,_T,Total,_T,Total,_T,Total,PCNT,Percent,2019,57.344059",
    "TCD,Chad,ED_CR_L1,Completion rate primary,F,Female,_T,Total,_T,Total,PCNT,Percent,2019,50.1",       # sex split: skipped
    "TCD,Chad,ED_CR_L1,Completion rate primary,_T,Total,Q1,Poorest,_T,Total,PCNT,Percent,2019,30.0",    # wealth split: skipped
    "TCD,Chad,ED_CR_L1,Completion rate primary,_T,Total,_T,Total,_T,Total,PCNT,Percent,2019,99.0",      # second survey, same year: first wins
    "TCD,Chad,ED_CR_L1,Completion rate primary,_T,Total,_T,Total,_T,Total,PCNT,Percent,2014-08,45.5",   # year-month period
    "TCD,Chad,ED_ROFST_L1,Out-of-school rate primary,_T,Total,_T,Total,_T,Total,PCNT,Percent,2019,53.9",
    "TCD,Chad,ED_BAD,Broken,_T,Total,_T,Total,_T,Total,PCNT,Percent,2019,not-a-number",
    "TCD,Chad,ED_OLD,Too old,_T,Total,_T,Total,_T,Total,PCNT,Percent,1950,10",
])


def test_unicef_keeps_only_all_population_rows_one_per_year():
    recs = parse_unicef(CSV, "EDUCATION")
    got = {(r["indicator"], r["year"]): r["value"] for r in recs}
    assert got == {("Completion rate primary", 2019): 57.34, ("Completion rate primary", 2014): 45.5,
                   ("Out-of-school rate primary", 2019): 53.9}
    assert all(r["source"] == "UNICEF Data" and r["unit"] == "Percent" and r["region"] == "national" for r in recs)


def test_unicef_unexpected_shape_gives_nothing():
    assert parse_unicef("<html>error</html>", "EDUCATION") == [] and parse_unicef("", "EDUCATION") == []
    assert is_total({"SEX": "_T"}) and not is_total({"SEX": "M"})


UIS = {"hints": [], "records": [
    {"indicatorId": "GER.1", "geoUnit": "TCD", "year": 1971, "value": 31.318359375},
    {"indicatorId": "GER.1", "geoUnit": "TCD", "year": 1972, "value": None},
    {"indicatorId": "GER.1", "geoUnit": "TCD", "year": 1950, "value": 5.0},
    {"indicatorId": "CR.1", "geoUnit": "TCD", "year": 2000, "value": 18.1},
]}


def test_uis_parses_its_own_code_only_and_explains_empty_answers():
    recs = parse_uis(UIS, "GER.1")
    assert [(r["year"], r["value"]) for r in recs] == [(1971, 31.32)] and recs[0]["source"] == "UNESCO UIS"
    assert parse_uis({"records": "x"}, "GER.1") == [] and parse_uis(UIS, "NOPE") == []
    assert "could not be found" in describe_uis({"hints": [{"message": "The indicator could not be found, X"}]})
    assert describe_uis({"hints": [], "records": []}) == "no data for Chad"


def test_education_sources_report_failures_and_keep_other_series(monkeypatch, tmp_path):
    async def fake_fetch(client, url, params=None, **kw):
        if params["indicator"] == "GER.1":
            return UIS
        return {"hints": [{"message": "The indicator could not be found"}], "records": []}

    monkeypatch.setattr(EducationAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    agent = EducationAgent(ObservationRepository(database_path=tmp_path / 'e.db'))
    recs = asyncio.run(agent._collect_unesco_uis())
    assert recs and agent.source_errors and "UNESCO UIS" in agent.source_errors[0]

    monkeypatch.setattr(EducationAgent, "fetch_json_with_retry", staticmethod(lambda *a, **k: _none()))
    try:
        asyncio.run(EducationAgent(ObservationRepository(database_path=tmp_path / 'e.db'))._collect_unesco_uis())
        raise AssertionError("must raise when every series is empty")
    except RuntimeError as exc:
        assert "returned nothing" in str(exc)


async def _none():
    return None


def test_unicef_collect_retries_then_reports(monkeypatch, tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=CSV) if calls["n"] >= 2 else httpx.Response(503)

    real = httpx.AsyncClient
    monkeypatch.setattr(edu.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    async def no_sleep(_):
        return None

    monkeypatch.setattr(edu.asyncio, "sleep", no_sleep)
    recs = asyncio.run(EducationAgent(ObservationRepository(database_path=tmp_path / 'e.db'))._collect_unicef_sdg4())
    assert calls["n"] == 2 and len(recs) == 3


def test_health_collects_unicef_nutrition_and_immunisation(monkeypatch, tmp_path):
    from app.agents import unicef as uni
    from app.agents.health import HealthAgent

    asked: list[str] = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(200, text=CSV)

    real = httpx.AsyncClient
    monkeypatch.setattr(uni.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    agent = HealthAgent(ObservationRepository(database_path=tmp_path / "h.db"))
    recs = asyncio.run(agent._collect_unicef())
    assert len(asked) == 2 and "NUTRITION" in asked[0] and "IMMUNISATION" in asked[1]
    assert recs and all(r["source"] == "UNICEF Data" for r in recs)


def test_unicef_names_fit_the_database_column():
    long_name = "x" * 150
    csv_text = HEADER + f"\nTCD,Chad,ED_LONG,{long_name},_T,Total,_T,Total,_T,Total,PCNT,Percent,2019,1.5"
    assert len(parse_unicef(csv_text, "EDUCATION")[0]["indicator"]) <= 100


def _row(code, year, age, value, prio="1", extra=""):
    return (f"TCD,Chad,{code},{code} name,_T,Total,_T,Total,_T,Total,PCNT,Percent,{year},{value},{age},{prio},C{extra}")


H2 = HEADER + ",AGE,DATA_SOURCE_PRIORITY,REPORTING_LVL"


def test_unicef_prefers_all_ages_row_and_skips_ambiguous_age_groups():
    text = "\n".join([
        H2,
        _row("NT_STUNT", 2022, "M6T11", 18.9), _row("NT_STUNT", 2022, "_T", 31.92), _row("NT_STUNT", 2022, "M12T23", 36.9),
        _row("IM_DTP3", 2024, "M12T23", 68),                                  # one age group only: accepted
        _row("NT_SPLIT", 2021, "M0T5", 16.2), _row("NT_SPLIT", 2021, "M6T11", 1.4),  # several ages, no total: skipped
    ])
    got = {r["indicator"]: r["value"] for r in parse_unicef(text, "NUTRITION")}
    assert got == {"NT_STUNT name": 31.92, "IM_DTP3 name": 68.0}


def test_unicef_drops_targets_future_years_and_non_national_levels_and_ranks_sources():
    text = "\n".join([
        H2,
        _row("TRGT_2030_NT_X", 2030, "_T", 12), _row("NT_FUT", 2099, "_T", 5),
        _row("NT_SUB", 2019, "_T", 40).replace(",C", ",S"),
        _row("NT_TWO", 2019, "_T", 10, prio="3"), _row("NT_TWO", 2019, "_T", 20, prio="1"),
    ])
    assert {r["indicator"]: r["value"] for r in parse_unicef(text, "NUTRITION")} == {"NT_TWO name": 20.0}
