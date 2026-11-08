"""World Bank Pink Sheet: layout of the real workbook (Nov 2026), link discovery, collector, monthly storage."""
import asyncio
from io import BytesIO

import httpx
import openpyxl
import pytest

from app.agents import TradeAgent
from app.agents.pink_sheet import COMMODITIES, find_workbook_url, parse_pink_sheet
from app.services.storage import ObservationRepository

REAL_CLIENT = httpx.AsyncClient
PAGE = '<a href="https://thedocs.worldbank.org/en/doc/74e8be-0050012026/related/CMO-Historical-Data-Monthly.xlsx">Monthly</a>'


def workbook(header=("Crude oil, average", "Maize", "Sorghum **", "Cocoa"), units=("($/bbl)", "($/mt)", "($/mt)", "($/kg)"), rows=None):
    wb = openpyxl.Workbook()
    wb.active.title = "Monthly Prices"
    ws = wb.active
    for _ in range(3):
        ws.append(["World Bank Commodity Price Data"])
    ws.append(["Updated on November 03, 2026"])
    ws.append([None, *header])
    ws.append([None, *units])
    for r in rows or [("1960M01", 1.6, "…", "..", 0.63), ("2000M01", 24.5, 83.5, 90.0, 0.9),
                      ("2026M10", 108.5, 232.0, 250.0, 6.1), ("2026M13", 1, 1, 1, 1)]:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_finds_the_workbook_link_in_the_page():
    assert find_workbook_url(PAGE).endswith("CMO-Historical-Data-Monthly.xlsx")
    assert find_workbook_url("<html>nothing</html>") is None and find_workbook_url("") is None


def test_parses_names_units_months_and_skips_gaps():
    rows = parse_pink_sheet(workbook())
    got = {(r["indicator"], r["year"], r["month"]): (r["value"], r["unit"]) for r in rows}
    assert got[("World price, crude oil (average)", 2026, 10)] == (108.5, "US$/bbl")
    assert got[("World price, sorghum", 2000, 1)] == (90.0, "US$/mt")           # "**" in the header is ignored
    assert not any(r["year"] < 2000 or r["month"] > 12 for r in rows)          # 1960 and "2026M13" dropped
    assert not any(r["indicator"].endswith("Cocoa") for r in rows)             # not in the Chad list
    assert all(r["region"] == "international" and r["source"] == "World Bank Pink Sheet" for r in rows)


def test_unexpected_layouts_raise_a_clear_error():
    wb = openpyxl.Workbook()
    wb.active.title = "Other"
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="Monthly Prices"):
        parse_pink_sheet(buf.getvalue())
    with pytest.raises(ValueError, match="header row"):
        parse_pink_sheet(workbook(header=("Cocoa", "Coffee"), units=("($/kg)", "($/kg)")))


def test_every_commodity_name_is_unique():
    assert len(set(COMMODITIES.values())) == len(COMMODITIES)


def _fake_client(monkeypatch, page=PAGE, xlsx=None, xlsx_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".xlsx"):
            return httpx.Response(xlsx_status, content=xlsx if xlsx is not None else workbook())
        return httpx.Response(200, text=page)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: REAL_CLIENT(**{**kw, "transport": httpx.MockTransport(handler)}))
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: asyncio.sleep(0))


def test_trade_stores_monthly_prices_with_their_licence(monkeypatch, tmp_path):
    _fake_client(monkeypatch)
    repo = ObservationRepository(database_path=tmp_path / "t.db")
    result = asyncio.run(TradeAgent(repo).run("pink-sheet"))
    rows = [r for r in repo.list_observations(sector="trade", limit=500) if r["indicator"] == "World price, maize"]
    assert result.stored == 6 and {r["reference_date"] for r in rows} == {"2000-01-01", "2026-10-01"}
    assert rows[0]["license"] == "CC BY 4.0" and rows[0]["region"] == "international"


def test_trade_reports_why_the_workbook_is_missing(monkeypatch, tmp_path):
    _fake_client(monkeypatch, page="<html>moved</html>")
    agent = TradeAgent(ObservationRepository(database_path=tmp_path / "t.db"))
    with pytest.raises(RuntimeError, match="link was not found"):
        asyncio.run(agent.collect("pink-sheet"))
    _fake_client(monkeypatch, xlsx=b"not a workbook")
    with pytest.raises(RuntimeError, match="not readable"):
        asyncio.run(agent.collect("pink-sheet"))


def test_all_keeps_world_bank_data_when_the_pink_sheet_fails(monkeypatch, tmp_path):
    _fake_client(monkeypatch, page="<html>moved</html>")
    agent = TradeAgent(ObservationRepository(database_path=tmp_path / "t.db"))

    async def wb():
        return [{"year": 2022, "value": 1.0, "source": "World Bank", "indicator": "Merchandise exports", "unit": "USD", "region": "national"}]
    monkeypatch.setattr(agent, "_collect_world_bank", wb)
    out = asyncio.run(agent.collect("all"))
    assert len(out) == 1 and any("Pink Sheet" in e for e in agent.source_errors)


def test_unknown_source_lists_the_new_one(tmp_path):
    with pytest.raises(ValueError, match="pink-sheet"):
        asyncio.run(TradeAgent(ObservationRepository(database_path=tmp_path / "t.db")).collect("nope"))
