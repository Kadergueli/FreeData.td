"""OpenStreetMap per region, IMF DataMapper, WFP prices from HDX: parsing, error reporting, terms.
No network: the HTTP layer is replaced by canned answers."""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents import osm
from app.agents.economy import EconomyAgent
from app.agents.education import EducationAgent
from app.agents.health import HealthAgent
from app.agents.imf import IMF_INDICATORS, parse_imf
from app.agents.markets import MarketsAgent
from app.agents.transport import TransportAgent
from app.agents.wfp_prices import parse_wfp_csv, pick_csv_url


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- OpenStreetMap
def _counts(*totals):
    return {"elements": [{"type": "count", "id": 0, "tags": {"nodes": "0", "ways": "0", "total": str(t)}} for t in totals]}


def test_query_has_one_count_per_feature_and_the_iso_area():
    q = osm.build_query("TD-LC", osm.SCHOOLS)
    assert 'area["ISO3166-2"="TD-LC"]' in q and q.count("out count;") == 1 and "~" not in q
    union = osm.build_query("TD-LC", osm.MAIN_ROADS)
    assert union.count("(area.a);") == 2 and "~" not in union      # exact tags, unioned


def test_parse_counts_checks_the_shape():
    assert osm.parse_counts(_counts(4, 2), 2) == [4, 2]
    assert osm.parse_counts(_counts(4), 2) is None
    assert osm.parse_counts({"remark": "runtime error"}, 1) is None
    assert osm.parse_counts(None, 1) is None


def _fake_query(answers):
    async def fake(client, query):
        iso = query.split('"ISO3166-2"="')[1].split('"')[0]
        return answers(iso)
    return fake


def test_collect_osm_counts_builds_regional_records(monkeypatch):
    seen = []

    async def fake(client, query):
        seen.append(query)
        return (_counts(0), "") if "aerodrome" in query else (_counts(7), "")
    monkeypatch.setattr(osm, "_query", fake)
    errors: list[str] = []
    records = run(osm.collect_osm_counts([osm.SCHOOLS, osm.MAIN_ROADS, osm.AERODROMES], errors, pause=0))
    # schools: one query per region; roads and aerodromes: ONE national query each (too slow per region)
    assert len(seen) == len(osm.REGIONS) + 2
    assert sum('"ISO3166-1"="TD"' in q for q in seen) == 2
    schools = [r for r in records if r["unit"] == "schools"]
    assert {r["region"] for r in schools} == set(osm.REGIONS.values()) and schools[0]["value"] == 7.0
    roads = [r for r in records if r["unit"] == "segments"]
    assert len(roads) == 1 and roads[0]["region"] == "national"      # the zero aerodrome count is not stored
    assert schools[0]["source"] == "OpenStreetMap" and errors == []


def test_partial_failure_is_reported_not_hidden(monkeypatch):
    def answers(iso):
        return (None, "HTTP 504") if iso in ("TD-LC", "TD-TI") else (_counts(3), "")
    monkeypatch.setattr(osm, "_query", _fake_query(answers))
    errors: list[str] = []
    records = run(osm.collect_osm_counts([osm.SCHOOLS], errors, pause=0))
    assert len(records) == len(osm.REGIONS) - 2
    assert "2/23 queries did not answer" in errors[0] and "HTTP 504" in errors[0]


def test_unresolved_area_is_skipped_and_noted(monkeypatch):
    monkeypatch.setattr(osm, "_query", _fake_query(lambda iso: (_counts(0), "") if iso == "TD-BO" else (_counts(2), "")))
    errors: list[str] = []
    records = run(osm.collect_osm_counts([osm.SCHOOLS], errors, pause=0))
    assert "Borkou" not in {r["region"] for r in records} and "Borkou" in errors[0]


def test_total_failure_raises(monkeypatch):
    monkeypatch.setattr(osm, "_query", _fake_query(lambda iso: (None, "HTTP 429")))
    with pytest.raises(RuntimeError, match="queries did not answer"):
        run(osm.collect_osm_counts([osm.SCHOOLS], [], pause=0))


def test_osm_rows_carry_the_odbl_licence():
    agent = HealthAgent(SimpleNamespace())
    obs = agent.normalize({"year": 2026, "month": 10, "day": 1, "value": 12.0, "source": "OpenStreetMap",
                           "indicator": osm.HOSPITALS.indicator, "unit": "facilities", "region": "Lac"})
    assert obs.license == "ODbL 1.0" and "OpenStreetMap contributors" in obs.notes


@pytest.mark.parametrize("agent_cls,method", [(HealthAgent, "_collect_open_street_map"),
                                              (EducationAgent, "_collect_open_street_map")])
def test_osm_failure_shows_in_the_run_errors(monkeypatch, agent_cls, method):
    agent = agent_cls(SimpleNamespace())

    async def ok():
        return []

    async def boom():
        raise RuntimeError("OpenStreetMap: 23/23 regions did not answer")
    for name in ("_collect_world_bank", "_collect_unesco_uis", "_collect_unicef_sdg4", "_collect_open_meteo_transport"):
        if hasattr(agent, name):
            monkeypatch.setattr(agent, name, ok)
    monkeypatch.setattr(agent, method, boom)
    run(agent.collect("all"))
    assert any("open-street-map" in e and "23/23" in e for e in agent.source_errors)


def test_the_dataset_counting_hdx_collectors_are_gone():
    for cls in (TransportAgent, EducationAgent, MarketsAgent):
        assert not hasattr(cls, "_collect_hdx_transport") and not hasattr(cls, "_collect_hdx_education")
    with pytest.raises(ValueError):
        run(TransportAgent(SimpleNamespace()).collect("hdx"))


# ---------------------------------------------------------------- IMF
def test_parse_imf_flags_projections_and_ignores_junk():
    payload = {"values": {"NGDP_RPCH": {"TCD": {"2009": 1.0, "2023": 4.9, "2026": 3.1, "2027": None, "x": 2}}}}
    rows = parse_imf(payload, "NGDP_RPCH", current_year=2026)
    assert {(r["year"], r["indicator"]) for r in rows} == {
        (2023, "Real GDP growth (IMF)"), (2026, "Real GDP growth (IMF)")}
    assert parse_imf({"values": {}}, "NGDP_RPCH") == [] and parse_imf(None, "NGDP_RPCH") == []
    future = parse_imf({"values": {"NGDP_RPCH": {"TCD": {"2030": 5}}}}, "NGDP_RPCH", current_year=2026)
    assert future[0]["indicator"].endswith("(projection)")


def _imf_agent(monkeypatch, fetch):
    agent = EconomyAgent(SimpleNamespace())
    monkeypatch.setattr(EconomyAgent, "fetch_json_with_retry", staticmethod(fetch))
    return agent


def test_imf_collection_and_terms(monkeypatch):
    async def fetch(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        code = url.split("/")[-2]
        return {"values": {code: {"TCD": {"2022": 1.5}}}}
    agent = _imf_agent(monkeypatch, fetch)
    rows = run(agent._collect_imf())
    assert len(rows) == len(IMF_INDICATORS) and agent.source_errors == []
    obs = agent.normalize(rows[0])
    assert obs.source == "IMF" and obs.license == "IMF terms of use"


def test_imf_partial_and_total_failure(monkeypatch):
    async def partial(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        code = url.split("/")[-2]
        if code == "BCA_NGDPD":
            if errors is not None:
                errors[:] = ["HTTP 404"]
            return None
        return {"values": {code: {"TCD": {"2022": 1.5}}}}
    agent = _imf_agent(monkeypatch, partial)
    run(agent._collect_imf())
    assert f"1/{len(IMF_INDICATORS)} series empty" in agent.source_errors[0] and "BCA_NGDPD (HTTP 404)" in agent.source_errors[0]

    async def dead(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        return None
    with pytest.raises(RuntimeError):
        run(_imf_agent(monkeypatch, dead)._collect_imf())


# ---------------------------------------------------------------- WFP / HDX
CSV = """date,admin1,admin2,market,latitude,longitude,category,commodity,unit,priceflag,pricetype,currency,price,usdprice
#date,#adm1+name,#adm2+name,#loc+market+name,#geo+lat,#geo+lon,#item+type,#item+name,#item+unit,#item+price+flag,#item+price+type,#currency,#value,#value+usd
2021-01-15,Lac,Bol,Bol,13.4,14.7,cereals,Maize,KG,actual,Retail,XAF,250,0.45
2023-05-15,Lac,Bol,Bol,13.4,14.7,cereals,Maize,KG,actual,Retail,XAF,310,0.50
2023-05-15,Lac,Bol,Bol,13.4,14.7,cereals,Maize,KG,actual,Retail,XAF,999,0.99
2023-05-15,Lac,Bol,Bol,13.4,14.7,cereals,Rice,KG,actual,Wholesale,XAF,400,0.60
2023-06-15,Lac,Bol,Bol,13.4,14.7,cereals,Rice,KG,actual,Retail,USD,0.7,0.7
2024-08-15,Guera,Mongo,Mongo,12.1,18.7,cereals,Sorghum,KG,actual,Retail,XAF,280,0.47
2024-08-15,Guera,Mongo,Mongo,12.1,18.7,cereals,Millet,KG,actual,Retail,XAF,abc,0.47
"""


def test_parse_wfp_csv_window_filters_and_dedup():
    rows, skipped = parse_wfp_csv(CSV, history_years=3)
    got = {(r["year"], r["month"], r["indicator"], r["value"], r["region"]) for r in rows}
    assert got == {(2023, 5, "Maize retail price (WFP)", 310.0, "Bol (Lac)"),
                   (2024, 8, "Sorghum retail price (WFP)", 280.0, "Mongo (Guera)")}
    assert skipped == 4          # duplicate, wholesale, USD, bad value (2021 is outside the window, not "skipped")
    assert all(r["unit"] == "XAF/KG" and r["source"] == "WFP" for r in rows)
    assert parse_wfp_csv("", 3) == ([], 0)


def test_pick_csv_url_prefers_the_full_file():
    pkg = {"result": {"resources": [
        {"name": "QuickCharts: Chad - Food Prices", "format": "CSV", "download_url": "https://x/quick.csv"},
        {"name": "Chad - Food Prices", "format": "CSV", "download_url": "https://x/full.csv"}]}}
    assert pick_csv_url(pkg) == "https://x/full.csv"
    assert pick_csv_url({"result": {"resources": []}}) is None and pick_csv_url(None) is None


def _wfp_agent(monkeypatch, package, text):
    agent = MarketsAgent(SimpleNamespace())

    async def fetch_json(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        if package is None and errors is not None:
            errors[:] = ["HTTP 503"]
        return package

    async def fetch_text(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15):
        return text
    monkeypatch.setattr(MarketsAgent, "fetch_json_with_retry", staticmethod(fetch_json))
    monkeypatch.setattr(MarketsAgent, "fetch_text_with_retry", staticmethod(fetch_text))
    return agent


def test_wfp_collection_end_to_end(monkeypatch):
    pkg = {"result": {"resources": [{"name": "Chad - Food Prices", "format": "CSV", "download_url": "https://x/full.csv"}]}}
    agent = _wfp_agent(monkeypatch, pkg, CSV)
    rows = run(agent._collect_wfp_prices())
    obs = agent.normalize(rows[0])
    assert obs.sector == "markets" and obs.license == "CC BY-IGO 3.0" and "World Food Programme" in obs.notes


@pytest.mark.parametrize("package,text,message", [
    (None, "", "HDX catalogue did not answer .*HTTP 503"),
    ({"result": {"resources": []}}, "", "no CSV file"),
    ({"result": {"resources": [{"name": "p", "format": "CSV", "url": "https://x/p.csv"}]}}, "", "could not be downloaded"),
    ({"result": {"resources": [{"name": "p", "format": "CSV", "url": "https://x/p.csv"}]}}, "date,price\n", "no usable"),
])
def test_wfp_failures_are_explicit(monkeypatch, package, text, message):
    with pytest.raises(RuntimeError, match=message):
        run(_wfp_agent(monkeypatch, package, text)._collect_wfp_prices())


def test_probe_sources_reports_each_source(monkeypatch):
    from app import cli

    async def none(self):
        raise RuntimeError("down")

    async def fake_query(client, query):
        return None, "HTTP 403"
    monkeypatch.setattr(EconomyAgent, "_collect_imf", none)
    monkeypatch.setattr(MarketsAgent, "_collect_wfp_prices", none)
    monkeypatch.setattr(TransportAgent, "_collect_airports", none)
    monkeypatch.setattr(osm, "_query", fake_query)
    out = run(cli.probe_sources())
    assert "IMF: FAILED - down" in out and "WFP (HDX): FAILED - down" in out and "OurAirports: FAILED - down" in out
    assert "HTTP 403" in out


# ---------------------------------------------------------------- a collection must always end
def test_osm_stops_early_when_the_first_requests_all_fail(monkeypatch):
    calls = []

    async def fake(client, query):
        calls.append(query)
        return None, "HTTP 504"
    monkeypatch.setattr(osm, "_query", fake)
    errors: list[str] = []
    with pytest.raises(RuntimeError, match="stopped early: the source is not answering"):
        run(osm.collect_osm_counts([osm.SCHOOLS], errors, pause=0))
    assert len(calls) <= osm.MAX_FIRST_FAILURES + osm.CONCURRENCY      # not 23 x slow retries


def test_osm_global_deadline_ends_a_hanging_server(monkeypatch):
    async def hang(client, query):
        await asyncio.sleep(60)
    monkeypatch.setattr(osm, "_query", hang)
    errors: list[str] = []
    import time
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="time limit reached"):
        run(osm.collect_osm_counts([osm.SCHOOLS], errors, pause=0, deadline_seconds=0.3))
    assert time.monotonic() - started < 5


def test_osm_never_runs_more_than_two_requests_at_once(monkeypatch):
    live = {"now": 0, "max": 0}

    async def fake(client, query):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        await asyncio.sleep(0.01)
        live["now"] -= 1
        return _counts(3), ""
    monkeypatch.setattr(osm, "_query", fake)
    run(osm.collect_osm_counts([osm.SCHOOLS], [], pause=0))
    assert live["max"] == osm.CONCURRENCY


def test_a_sector_that_never_finishes_is_stopped_by_the_harvest(monkeypatch):
    from app.services import scheduler as sched

    class Hanging:
        def __init__(self, repo): pass
        async def run(self, source="all"):
            await asyncio.sleep(60)

    monkeypatch.setattr(sched, "SECTOR_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(sched, "TransportAgent", Hanging)
    service = sched.AutonomousHarvesterScheduler(interval_hours=24)
    service._next_sectors = ["transport"]
    result = run(service._run_harvest_job())
    assert "stopped after" in result["sectors"]["transport"]["error"]


def test_transport_all_does_not_wait_for_the_national_osm_queries(monkeypatch):
    agent = TransportAgent(SimpleNamespace())
    called = []

    async def ok():
        return []

    async def osm_never():
        called.append("osm")
        return []
    monkeypatch.setattr(agent, "_collect_world_bank", ok)
    monkeypatch.setattr(agent, "_collect_airports", ok)
    monkeypatch.setattr(agent, "_collect_open_meteo_transport", ok)
    monkeypatch.setattr(agent, "_collect_open_street_map", osm_never)
    run(agent.collect("all"))
    assert called == []
    run(agent.collect("open-street-map"))          # still possible on purpose
    assert called == ["osm"]


def test_a_failure_already_reported_by_the_collector_is_not_repeated(monkeypatch):
    agent = HealthAgent(SimpleNamespace())

    async def ok():
        return []

    async def boom():
        agent.source_errors.append("OpenStreetMap: 5/23 queries did not answer")
        raise RuntimeError("OpenStreetMap: 5/23 queries did not answer")
    monkeypatch.setattr(agent, "_collect_world_bank", ok)
    monkeypatch.setattr(agent, "_collect_open_street_map", boom)
    run(agent.collect("all"))
    assert agent.source_errors == ["OpenStreetMap: 5/23 queries did not answer"]


# ---------------------------------------------------------------- OurAirports
AIRPORTS_CSV = """id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,gps_code
1,FTTJ,medium_airport,N'Djamena Hassan Djamous,12.13,15.03,968,AF,TD,TD-ND,N'Djamena,yes,FTTJ
2,FTTA,small_airport,Sarh,9.14,18.37,1198,AF,TD,TD-MC,Sarh,yes,FTTA
3,FTTB,small_airport,Bol,13.45,14.7,900,AF,TD,TD-LC,Bol,no,
4,FTHP,heliport,Heli,12.0,15.0,900,AF,TD,TD-ND,,no,
5,FTXX,closed,Old strip,12.0,15.0,900,AF,TD,TD-ND,,no,
6,DNMM,large_airport,Lagos,6.5,3.3,135,AF,NG,NG-LA,Lagos,yes,DNMM
7,FTYY,small_airport,Unknown region,12.0,15.0,900,AF,TD,TD-ZZ,,no,
"""


def test_parse_airports_counts_per_region_and_nationally():
    from app.agents.airports import parse_airports
    rows = parse_airports(AIRPORTS_CSV)
    by = {(r["region"], r["indicator"]): r["value"] for r in rows}
    assert by[("N'Djamena", "Airports and airstrips (OurAirports)")] == 1.0
    assert by[("Lac", "Airports and airstrips (OurAirports)")] == 1.0
    assert by[("national", "Airports and airstrips (OurAirports)")] == 4.0           # heliport, closed, Nigeria left out
    assert by[("national", "Airports with scheduled service (OurAirports)")] == 2.0
    assert parse_airports("id,iso_country\n") == []


def _airports_agent(monkeypatch, text):
    agent = TransportAgent(SimpleNamespace())

    async def fetch_text(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15):
        return text
    monkeypatch.setattr(TransportAgent, "fetch_text_with_retry", staticmethod(fetch_text))
    return agent


def test_airports_collection_terms_and_failures(monkeypatch):
    agent = _airports_agent(monkeypatch, AIRPORTS_CSV)
    rows = run(agent._collect_airports())
    obs = agent.normalize(rows[0])
    assert obs.sector == "transport" and obs.license == "Public domain" and "OurAirports" in obs.notes
    with pytest.raises(RuntimeError, match="could not be downloaded"):
        run(_airports_agent(monkeypatch, None)._collect_airports())
    with pytest.raises(RuntimeError, match="no airport found"):
        run(_airports_agent(monkeypatch, "id,iso_country\n1,FR\n")._collect_airports())
