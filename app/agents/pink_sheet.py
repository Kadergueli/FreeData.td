"""World Bank Commodity Price Data ("Pink Sheet"): monthly world prices since 1960 (CC BY 4.0).

The workbook link changes with every release, so it is read from the commodity-markets page each time:
    https://www.worldbank.org/en/research/commodity-markets  ->  .../CMO-Historical-Data-Monthly.xlsx
Sheet "Monthly Prices": row 5 holds the names, row 6 the units ("($/mt)"), then one row per month whose
first cell is "2026M10". Missing values are written "…" or "..".
"""
from __future__ import annotations

from io import BytesIO
import re
from typing import Any

PAGE_URL = "https://www.worldbank.org/en/research/commodity-markets"
LINK_RE = re.compile(r"https://[^\"'\s<>]+CMO-Historical-Data-Monthly\.xlsx")
SOURCE = "World Bank Pink Sheet"
FIRST_YEAR = 2000

# Header of the sheet (trailing spaces and "**" removed) -> indicator name. The ones that matter for Chad:
# oil and cotton (exports), cereals, oils and meat (the food basket), fertiliser (farm costs), gold.
COMMODITIES: dict[str, str] = {
    "Crude oil, average": "World price, crude oil (average)",
    "Maize": "World price, maize",
    "Sorghum": "World price, sorghum",
    "Rice, Thai 5%": "World price, rice (Thai 5%)",
    "Wheat, US HRW": "World price, wheat (US HRW)",
    "Groundnuts": "World price, groundnuts",
    "Groundnut oil": "World price, groundnut oil",
    "Palm oil": "World price, palm oil",
    "Soybean oil": "World price, soybean oil",
    "Sugar, world": "World price, sugar",
    "Cotton, A Index": "World price, cotton (A Index)",
    "Beef": "World price, beef",
    "Chicken": "World price, chicken",
    "Urea": "World price, urea (fertiliser)",
    "DAP": "World price, DAP (fertiliser)",
    "Gold": "World price, gold",
}


def find_workbook_url(page_html: str) -> str | None:
    match = LINK_RE.search(page_html or "")
    return match.group(0) if match else None


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().rstrip("*").strip()


def _unit(text: Any) -> str:
    raw = str(text or "").strip().strip("()").strip()
    return ("US" + raw)[:40] if raw.startswith("$") else raw[:40]


def parse_pink_sheet(content: bytes, first_year: int = FIRST_YEAR, url: str | None = None) -> list[dict[str, Any]]:
    """Records (month, value) for the commodities above; raises ValueError when the layout is not the expected one."""
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    if "Monthly Prices" not in wb.sheetnames:
        raise ValueError(f"no 'Monthly Prices' sheet (sheets: {', '.join(wb.sheetnames)})")
    rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
    header_at = next((i for i, r in enumerate(rows[:15]) if r and any(_clean(c) == "Crude oil, average" for c in r)), None)
    if header_at is None or header_at + 1 >= len(rows):
        raise ValueError("header row with 'Crude oil, average' not found")
    columns = {i: (COMMODITIES[_clean(c)], _unit(rows[header_at + 1][i]))
               for i, c in enumerate(rows[header_at]) if _clean(c) in COMMODITIES}
    if not columns:
        raise ValueError("none of the expected commodities found")
    out: list[dict[str, Any]] = []
    for row in rows[header_at + 2:]:
        m = re.fullmatch(r"(\d{4})M(\d{2})", str(row[0] or "").strip()) if row else None
        if not m or int(m.group(1)) < first_year or not 1 <= int(m.group(2)) <= 12:
            continue
        for i, (name, unit) in columns.items():
            value = row[i] if i < len(row) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append({"year": int(m.group(1)), "month": int(m.group(2)), "value": round(float(value), 2),
                            "source": SOURCE, "indicator": name, "unit": unit, "region": "international", "url": url})
    return out
