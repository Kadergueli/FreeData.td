"""WFP food prices for Chad, published on the Humanitarian Data Exchange (HDX).

The old WFP VAM API no longer answers, but WFP publishes the same monthly market prices as a CSV
on HDX (dataset `wfp-food-prices-for-chad`, licence CC BY-IGO). The CKAN API of HDX gives the
current download address of the file:

    GET https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-chad

The CSV has a second line of HXL tags (`#date`, `#adm1+name`...) that is skipped. Columns used:
date, admin1, market, commodity, unit, pricetype, currency, price.
"""
from __future__ import annotations

import csv
from io import StringIO
from typing import Any

HDX_PACKAGE_URL = "https://data.humdata.org/api/3/action/package_show"
HDX_PACKAGE_ID = "wfp-food-prices-for-chad"
SOURCE_LABEL = "WFP"


def pick_csv_url(package: Any) -> str | None:
    """Address of the full price file: the CSV resource that is not the 'QuickCharts' extract."""
    resources = ((package or {}).get("result") or {}).get("resources") if isinstance(package, dict) else None
    for resource in resources or []:
        if not isinstance(resource, dict):
            continue
        name = str(resource.get("name", "")).lower()
        if str(resource.get("format", "")).lower() != "csv" or "quickcharts" in name:
            continue
        url = resource.get("download_url") or resource.get("url")
        if url:
            return str(url)
    return None


def parse_wfp_csv(text: str, history_years: int = 3) -> tuple[list[dict[str, Any]], int]:
    """Raw records for the last `history_years` calendar years present in the file (retail prices
    in XAF only), and the number of rows skipped (duplicates, other currencies, bad values)."""
    rows = []
    for row in csv.DictReader(StringIO(text.lstrip("\ufeff"))):
        stamp = str(row.get("date", "")).strip()
        if len(stamp) >= 7 and stamp[:4].isdigit() and stamp[4] == "-":     # drops the HXL line
            rows.append((stamp, row))
    if not rows:
        return [], 0
    first_year = max(int(stamp[:4]) for stamp, _ in rows) - history_years + 1

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    skipped = 0
    for stamp, row in rows:
        year, month = int(stamp[:4]), int(stamp[5:7]) if stamp[5:7].isdigit() else 1
        if year < first_year:
            continue
        market = str(row.get("market", "")).strip()
        commodity = str(row.get("commodity", "")).strip()
        currency = str(row.get("currency", "")).strip().upper()
        pricetype = str(row.get("pricetype", "")).strip().lower()
        try:
            price = float(str(row.get("price", "")).replace(",", ""))
        except ValueError:
            skipped += 1
            continue
        if not market or not commodity or currency != "XAF" or price <= 0 or pricetype not in ("", "retail"):
            skipped += 1
            continue
        key = (stamp[:7], market, commodity)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        admin1 = str(row.get("admin1", "")).strip()
        unit = str(row.get("unit", "")).strip() or "KG"
        records.append({
            "year": year, "month": month, "day": 1, "value": round(price, 2),
            "source": SOURCE_LABEL, "indicator": f"{commodity} retail price (WFP)",
            "unit": f"XAF/{unit}"[:30], "region": f"{market} ({admin1})" if admin1 else market,
            "url": f"https://data.humdata.org/dataset/{HDX_PACKAGE_ID}",
        })
    return records, skipped
