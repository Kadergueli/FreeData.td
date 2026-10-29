"""Patch 0040 — real market prices (FEWS NET) replace the empty price collection."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app import cli
from app.agents import fews_prices
from app.agents.base import BaseAgent
from app.agents.fews_prices import extract_items, parse_record
from app.agents.markets import MarketsAgent

ROW = {"market": "Abéché", "admin_1": "Ouaddaï", "product": "Millet", "price_type": "Retail",
       "unit": "kg", "currency": "XOF", "period_date": "2026-09-30", "value": "425.5"}


def test_parse_record_builds_a_price_observation_input():
    rec = parse_record(ROW)
    assert rec["indicator"] == "Millet price (retail) - Abéché" and rec["region"] == "Ouaddaï"
    assert rec["unit"] == "XOF/kg" and rec["value"] == 425.5 and (rec["year"], rec["month"], rec["day"]) == (2026, 9, 30)
    assert rec["source"] == "FEWS NET" and "attribution" in rec["license"].lower()


def test_parse_record_without_admin_uses_the_market_as_region_and_keeps_the_indicator_short():
    rec = parse_record({**ROW, "admin_1": None})
    assert rec["region"] == "Abéché" and rec["indicator"] == "Millet price (retail)"


def test_parse_record_accepts_other_spellings_and_nested_objects():
    rec = parse_record({"market_name": {"name": "N'Djamena"}, "product_name": "Sorghum", "price": 300,
                        "date": "2026-08-31T00:00:00Z", "currency_code": "XAF", "unit_of_measure": "kg"})
    assert rec["value"] == 300.0 and rec["unit"] == "XAF/kg" and rec["region"] == "N'Djamena" and rec["month"] == 8


@pytest.mark.parametrize("bad", [
    {**ROW, "value": None}, {**ROW, "value": "0"}, {**ROW, "value": "-5"}, {**ROW, "value": "abc"},
    {**ROW, "period_date": None}, {**ROW, "period_date": "not-a-date"}, {**ROW, "product": None},
])
def test_unusable_rows_are_skipped_not_guessed(bad):
    assert parse_record(bad) is None


def test_extract_items_shapes():
    assert extract_items([ROW, "junk"]) == ([ROW], None)
    assert extract_items({"results": [ROW], "next": "https://x/?page=2"}) == ([ROW], "https://x/?page=2")
    assert extract_items({"results": [ROW], "next": None}) == ([ROW], None)
    with pytest.raises(ValueError):
        extract_items({"detail": "nope"})


def _agent(monkeypatch, pages):
    """MarketsAgent whose HTTP layer serves `pages` in order (None = request failed)."""
    calls = []

    async def fake_fetch(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        calls.append((url, params))
        return pages.pop(0)

    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    return MarketsAgent(SimpleNamespace()), calls


def test_collect_follows_pagination_and_uses_a_rolling_start(monkeypatch):
    agent, calls = _agent(monkeypatch, [
        {"results": [ROW], "next": "https://fdw.fews.net/api/marketpricefacts/?page=2"},
        {"results": [{**ROW, "period_date": "2026-08-31"}, {**ROW, "value": None}], "next": None},
    ])
    records = asyncio.run(agent._collect_fews_prices())
    assert len(records) == 2
    assert calls[0][1]["country_code"] == "TD" and calls[0][1]["start_date"].endswith("-01-01")
    assert int(calls[0][1]["start_date"][:4]) == __import__("datetime").datetime.now().year - 2   # moves with the calendar
    assert calls[1] == ("https://fdw.fews.net/api/marketpricefacts/?page=2", None)


def test_unreachable_api_raises_instead_of_returning_nothing(monkeypatch):
    agent, _ = _agent(monkeypatch, [None])
    with pytest.raises(RuntimeError, match="FEWS NET"):
        asyncio.run(agent._collect_fews_prices())


def test_one_failing_source_is_reported_in_the_run_result(monkeypatch):
    agent, _ = _agent(monkeypatch, [None])

    async def wb(): return [{"year": 2024, "value": 1.0, "indicator": "Trade volume", "unit": "% of GDP",
                              "source": "World Bank", "region": "national"}]
    async def none(): return []
    monkeypatch.setattr(agent, "_collect_world_bank", wb)
    monkeypatch.setattr(agent, "_collect_wfp_prices", none)
    monkeypatch.setattr(agent, "_collect_faostat_prices", none)
    monkeypatch.setattr(BaseAgent, "_archive_raw", lambda *a, **k: None)
    repo = SimpleNamespace(store_raw_batch=lambda *a, **k: None, upsert_many=lambda *a, **k: 1,
                           store_validation_report=lambda **k: None)
    agent.repository = repo
    result = asyncio.run(agent.run("all"))
    assert result.stored == 1 and any(e.startswith("source failed: fews-net") for e in result.errors)


def test_normalized_price_carries_licence_and_attribution():
    obs = MarketsAgent(SimpleNamespace()).normalize(parse_record(ROW))
    assert obs.source == "FEWS NET" and obs.license == fews_prices.LICENSE
    assert "FEWS NET" in obs.notes and "attribution" in obs.notes.lower()
    assert obs.region == "Ouaddai" and str(obs.reference_date) == "2026-09-30"


def test_the_empty_metadata_collector_is_gone():
    assert not hasattr(MarketsAgent, "_collect_hdx_ocha")
    with pytest.raises(ValueError):
        asyncio.run(MarketsAgent(SimpleNamespace()).collect("hdx"))


class _Resp:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text
        self.headers = {"content-type": "application/json"}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _patch_httpx(monkeypatch, response=None, error=None):
    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            if error: raise error
            return response
    monkeypatch.setattr(httpx, "AsyncClient", Client)


def test_probe_reports_success_with_fields_and_freshness(monkeypatch):
    _patch_httpx(monkeypatch, _Resp(200, {"results": [ROW], "next": None}))
    out = asyncio.run(cli.probe_prices())
    assert "HTTP 200" in out and "usable price records: 1 of 1" in out and "newest price date: 2026-09-30" in out
    assert "Millet" in out and "'market'" in out


@pytest.mark.parametrize("resp,expected", [
    (_Resp(403, text="forbidden"), "HTTP 403"),
    (_Resp(200, {"detail": "x"}, text="{}"), "UNREADABLE"),
    (_Resp(200, []), "EMPTY"),
    (_Resp(200, [{"foo": 1}]), "NONE USABLE"),
])
def test_probe_explains_each_failure(monkeypatch, resp, expected):
    _patch_httpx(monkeypatch, resp)
    assert expected in asyncio.run(cli.probe_prices())


def test_probe_reports_network_error(monkeypatch):
    _patch_httpx(monkeypatch, error=httpx.ConnectError("blocked"))
    assert "NETWORK ERROR" in asyncio.run(cli.probe_prices())


# ── same product / market / date listed twice (real FEWS NET data) ──
def _rec(unit, value, indicator="Maize price (retail)", region="Lac", d=(2026, 8, 31)):
    return {"year": d[0], "month": d[1], "day": d[2], "value": value, "indicator": indicator, "unit": unit, "region": region}


def test_collisions_are_told_apart_by_unit():
    from app.agents.fews_prices import resolve_collisions
    out, renamed, dropped = resolve_collisions([_rec("XAF/kg", 300), _rec("XAF/100kg", 28000)])
    assert renamed == 2 and dropped == 0
    assert sorted(r["indicator"] for r in out) == ["Maize price (retail) [100kg]", "Maize price (retail) [kg]"]


def test_identical_key_and_unit_keeps_the_last_row_only():
    from app.agents.fews_prices import resolve_collisions
    out, renamed, dropped = resolve_collisions([_rec("XAF/kg", 300), _rec("XAF/kg", 310)])
    assert len(out) == 1 and out[0]["value"] == 310 and dropped == 1 and renamed == 0


def test_no_collision_changes_nothing_and_keys_are_unique_after():
    from app.agents.fews_prices import resolve_collisions
    recs = [_rec("XAF/kg", 1), _rec("XAF/kg", 2, region="Batha"), _rec("XAF/kg", 3, d=(2026, 7, 31)),
            _rec("XAF/kg", 4), _rec("XAF/ea", 5)]
    out, _, _ = resolve_collisions(recs)
    keys = [(r["indicator"], r["region"], r["year"], r["month"], r["day"]) for r in out]
    assert len(keys) == len(set(keys))


def test_collector_hands_unique_rows_to_the_pipeline(monkeypatch):
    import asyncio

    from app.agents import markets
    payload = {"results": [
        {"value": 300, "period_date": "2026-08-31", "product": "Maize", "admin_1": "Lac", "unit": "kg", "currency": "XAF"},
        {"value": 28000, "period_date": "2026-08-31", "product": "Maize", "admin_1": "Lac", "unit": "100kg", "currency": "XAF"},
    ], "next": None}

    async def fake_fetch(self, client, url, **kw):
        return payload
    monkeypatch.setattr(markets.MarketsAgent, "fetch_json_with_retry", fake_fetch)
    records = asyncio.run(markets.MarketsAgent(None)._collect_fews_prices())
    assert len(records) == 2 and len({r["indicator"] for r in records}) == 2


# ── production failure: "did not answer" gave no reason ──
def _client_with(handler):
    import httpx
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_failure_reason_is_reported_for_http_errors():
    import httpx
    async def run():
        reasons = []
        async with _client_with(lambda req: httpx.Response(403, text="Forbidden by edge")) as c:
            got = await BaseAgent.fetch_json_with_retry(c, "https://x.test/", throttle_seconds=0, errors=reasons)
        return got, reasons
    got, reasons = asyncio.run(run())
    assert got is None and reasons and reasons[0].startswith("HTTP 403") and "Forbidden by edge" in reasons[0]


def test_failure_reason_is_reported_for_timeouts_and_reaches_the_run_error(monkeypatch):
    import httpx
    def boom(req):
        raise httpx.ReadTimeout("read timed out")
    monkeypatch.setattr("asyncio.sleep", lambda *a, **k: _noop())

    async def _noop():
        return None

    async def run():
        reasons = []
        async with _client_with(boom) as c:
            await BaseAgent.fetch_json_with_retry(c, "https://x.test/", throttle_seconds=0, max_retries=2, errors=reasons)
        return reasons
    assert asyncio.run(run())[0].startswith("ReadTimeout")

    async def fake_fetch(client, url, params=None, headers=None, max_retries=3, throttle_seconds=0.15, errors=None):
        errors.append("HTTP 403: 'blocked'")
        return None
    monkeypatch.setattr(BaseAgent, "fetch_json_with_retry", staticmethod(fake_fetch))
    with pytest.raises(RuntimeError, match=r"FEWS NET did not answer \(HTTP 403: 'blocked'\)"):
        asyncio.run(MarketsAgent(SimpleNamespace())._collect_fews_prices())
