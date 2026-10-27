"""Patch 0040 — real market prices from the FEWS NET API (answers simulated: the sandbox cannot reach it)."""
import asyncio

import pytest

from app.agents import fews_prices
from app.agents.fews_prices import extract_items, parse_record
from app.agents.markets import MarketsAgent

ROW = {"country_code": "TD", "market": "Abéché", "admin_1": "Ouaddaï", "product": "Millet", "price_type": "Retail",
       "unit": "kg", "currency": "XOF", "period_date": "2026-09-30", "value": 312.5}


def test_parse_standard_row():
    rec = parse_record(ROW)
    assert rec["indicator"] == "Millet price (retail) - Abéché"
    assert rec["region"] == "Ouaddaï" and rec["unit"] == "XOF/kg" and rec["value"] == 312.5
    assert (rec["year"], rec["month"], rec["day"]) == (2026, 9, 30)
    assert rec["source"] == "FEWS NET" and "attribution" in rec["license"]


def test_without_admin_region_the_market_is_the_region_and_not_repeated_in_the_indicator():
    rec = parse_record({**ROW, "admin_1": None})
    assert rec["region"] == "Abéché" and rec["indicator"] == "Millet price (retail)"


def test_alternative_spellings_and_nested_objects():
    rec = parse_record({"market_name": {"name": "N'Djamena"}, "product_name": "Sorghum", "price": "250", "date": "2025-03-31",
                        "currency_code": "XAF"})
    assert rec["region"] == "N'Djamena" and rec["value"] == 250.0 and rec["unit"] == "XAF/kg"


@pytest.mark.parametrize("bad", [
    {**ROW, "value": None}, {**ROW, "value": 0}, {**ROW, "value": -3}, {**ROW, "value": "n/a"},
    {**ROW, "period_date": None}, {**ROW, "period_date": "soon"}, {**ROW, "product": None},
])
def test_unusable_rows_are_ignored_not_stored_as_prices(bad):
    assert parse_record(bad) is None


def test_extract_items_list_paginated_and_garbage():
    assert extract_items([ROW, "x"]) == ([ROW], None)
    assert extract_items({"results": [ROW], "next": "https://x/?page=2"}) == ([ROW], "https://x/?page=2")
    assert extract_items({"results": [ROW], "next": None}) == ([ROW], None)
    with pytest.raises(ValueError):
        extract_items({"detail": "Authentication credentials were not provided."})


def _agent(monkeypatch, pages):
    """MarketsAgent whose HTTP layer returns the given pages in order."""
    calls = []

    async def fake_fetch(client, url, params=None, **kw):
        calls.append((url, params))
        return pages[len(calls) - 1] if len(calls) <= len(pages) else None

    agent = MarketsAgent(repository=None)
    monkeypatch.setattr(MarketsAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    return agent, calls


def test_collect_follows_pages_and_asks_for_chad_with_a_rolling_start(monkeypatch):
    agent, calls = _agent(monkeypatch, [{"results": [ROW], "next": "https://fdw.fews.net/api/marketpricefacts/?page=2"},
                                        {"results": [{**ROW, "product": "Rice"}], "next": None}])
    records = asyncio.run(agent._collect_fews_prices())
    assert [r["indicator"] for r in records] == ["Millet price (retail) - Abéché", "Rice price (retail) - Abéché"]
    first_params = calls[0][1]
    assert first_params["country_code"] == "TD" and first_params["format"] == "json"
    assert first_params["start_date"] == f"{__import__('datetime').datetime.now().year - 2}-01-01"
    assert calls[1][1] is None and "page=2" in calls[1][0]


def test_unreachable_api_raises_instead_of_returning_nothing(monkeypatch):
    agent, _ = _agent(monkeypatch, [])
    with pytest.raises(RuntimeError, match="FEWS NET did not answer"):
        asyncio.run(agent._collect_fews_prices())


def test_all_sources_failure_is_reported_in_the_run_but_other_sources_still_count(monkeypatch):
    agent = MarketsAgent(repository=None)

    async def ok(self): return [{"year": 2024, "value": 1.0, "source": "World Bank", "indicator": "Trade volume", "unit": "%", "region": "national"}]
    async def boom(self): raise RuntimeError("FEWS NET did not answer")
    async def none(self): return []
    monkeypatch.setattr(MarketsAgent, "_collect_world_bank", ok)
    monkeypatch.setattr(MarketsAgent, "_collect_fews_prices", boom)
    monkeypatch.setattr(MarketsAgent, "_collect_wfp_prices", none)
    monkeypatch.setattr(MarketsAgent, "_collect_faostat_prices", none)
    records = asyncio.run(agent.collect("all"))
    assert len(records) == 1
    assert agent.source_errors == ["fews-net: FEWS NET did not answer"]


def test_run_result_lists_failed_sources(monkeypatch, tmp_path):
    from app.services.storage import ObservationRepository
    repo = ObservationRepository(tmp_path / "x.db")
    agent = MarketsAgent(repo)
    monkeypatch.setattr(MarketsAgent, "_archive_raw", lambda *a, **k: None)

    async def collect(source):
        agent.source_errors.append("fews-net: down")
        return []
    monkeypatch.setattr(agent, "collect", collect)
    result = asyncio.run(agent.run("all"))
    assert any(e == "source failed: fews-net: down" for e in result.errors)


def test_normalized_price_keeps_licence_and_attribution():
    obs = MarketsAgent(repository=None).normalize(parse_record(ROW))
    assert obs.license == fews_prices.LICENSE and "Famine Early Warning" in obs.notes
    assert obs.indicator.startswith("Millet price") and obs.unit == "XOF/kg"


def test_no_junk_metadata_row_any_more():
    import inspect
    assert "Active market price datasets" not in inspect.getsource(MarketsAgent)


# --- probe-prices (run by the user on a machine that can reach the API) ---------------------------
class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._p, self.text = status, payload, text or str(payload)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._p


def _fake_client(resp=None, exc=None):
    class C:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None):
            if exc:
                raise exc
            return resp
    return C


def test_probe_reports_a_healthy_api(monkeypatch):
    import httpx
    from app.cli import probe_prices
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_Resp(200, {"results": [ROW, {**ROW, "product": "Rice"}], "next": None})))
    out = asyncio.run(probe_prices())
    assert "HTTP 200" in out and "usable price records: 2 of 2" in out and "newest price date: 2026-09-30" in out
    assert "Abéché" not in out or "Ouaddaï" in out


def test_probe_reports_unusable_field_names_and_http_errors(monkeypatch):
    import httpx
    from app.cli import probe_prices
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_Resp(200, [{"foo": 1}])))
    assert "NONE USABLE" in asyncio.run(probe_prices())
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_Resp(401, None, "Authentication credentials were not provided.")))
    out = asyncio.run(probe_prices())
    assert "HTTP 401" in out and "credentials" in out
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_Resp(200, {"detail": "x"})))
    assert "UNREADABLE" in asyncio.run(probe_prices())
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(exc=httpx.ConnectError("blocked")))
    assert "NETWORK ERROR" in asyncio.run(probe_prices())


def _inseed_resp(status, text, ctype="application/xml", server="cloudflare"):
    r = _Resp(status, None, text)
    r.content = text.encode()
    r.headers = {"content-type": ctype, "server": server}
    return r


def _no_sleep(monkeypatch):
    async def instant(_): return None
    monkeypatch.setattr("asyncio.sleep", instant)


def test_probe_inseed_saves_good_answers_and_shows_the_data_section(monkeypatch, tmp_path):
    import httpx
    from app.cli import INSEED_PROBES, probe_inseed
    _no_sleep(monkeypatch)
    xml = '<?xml version="1.0"?><Header/><DataSet><Series FREQ="A"><Obs TIME_PERIOD="2024" OBS_VALUE="1.5"/></Series></DataSet>'
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_inseed_resp(200, xml)))
    out = asyncio.run(probe_inseed(tmp_path))
    assert out.count("HTTP 200") == len(INSEED_PROBES) and "<DataSet>" in out and "OBS_VALUE" in out
    assert (tmp_path / "inseed_xxhsxif.xml").read_text(encoding="utf-8") == xml


def test_probe_inseed_calls_the_key_with_literal_plus_signs(monkeypatch, tmp_path):
    import httpx
    from app.cli import probe_inseed
    _no_sleep(monkeypatch)
    seen = []

    class C:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None):
            seen.append((url, headers))
            return _inseed_resp(200, "<DataSet/>")
    monkeypatch.setattr(httpx, "AsyncClient", C)
    asyncio.run(probe_inseed(tmp_path))
    assert seen[0][0] == "https://chad.opendataforafrica.org/api/1.0/sdmx/data/xxhsxif?key=PCPI_IX+PCPI_CP_01_IX.2019"
    assert all("FreeData.td" in h["User-Agent"] for _, h in seen)      # honest identification


def test_probe_inseed_reports_a_bot_challenge_without_dumping_html(monkeypatch, tmp_path):
    import httpx
    from app.cli import probe_inseed
    _no_sleep(monkeypatch)
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(_inseed_resp(403, "<html><title>Just a moment...</title>", "text/html")))
    out = asyncio.run(probe_inseed(tmp_path))
    assert "BLOCKED by a Cloudflare bot challenge" in out and "<html>" not in out
    assert not list(tmp_path.iterdir())


def test_probe_inseed_survives_network_errors(monkeypatch, tmp_path):
    import httpx
    from app.cli import probe_inseed
    _no_sleep(monkeypatch)
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client(exc=httpx.ConnectError("blocked")))
    assert "NETWORK ERROR" in asyncio.run(probe_inseed(tmp_path))
