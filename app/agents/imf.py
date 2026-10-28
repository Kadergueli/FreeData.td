"""IMF DataMapper (World Economic Outlook) series for Chad: public JSON API, no key.

    GET https://www.imf.org/external/datamapper/api/v1/{INDICATOR}/TCD
    -> {"values": {"NGDP_RPCH": {"TCD": {"2019": 3.2, "2020": -1.6, ...}}}}

Years after the current one are IMF projections: the indicator name says so.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

IMF_URL = "https://www.imf.org/external/datamapper/api/v1"
FIRST_YEAR = 2010

IMF_INDICATORS: dict[str, tuple[str, str]] = {
    "NGDP_RPCH": ("Real GDP growth (IMF)", "%"),
    "PCPIPCH": ("Inflation, average consumer prices (IMF)", "%"),
    "GGXWDG_NGDP": ("General government gross debt (IMF)", "% of GDP"),
    "GGR_NGDP": ("Government revenue (IMF)", "% of GDP"),
    "GGXCNL_NGDP": ("Government net lending/borrowing (IMF)", "% of GDP"),
    "BCA_NGDPD": ("Current account balance (IMF)", "% of GDP"),
    "NGDPD": ("GDP, current prices (IMF)", "billion USD"),
    "LUR": ("Unemployment rate (IMF)", "%"),
}


def parse_imf(payload: Any, code: str, current_year: int | None = None) -> list[dict[str, Any]]:
    """Raw records of one DataMapper answer (empty when the shape is not the expected one)."""
    current_year = current_year or datetime.now(UTC).year
    name, unit = IMF_INDICATORS[code]
    try:
        series = payload["values"][code]["TCD"]
    except (KeyError, TypeError):
        return []
    if not isinstance(series, dict):
        return []
    records: list[dict[str, Any]] = []
    for year_text, value in series.items():
        if not str(year_text).isdigit() or value is None:
            continue
        year = int(year_text)
        if year < FIRST_YEAR:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        records.append({
            "year": year, "value": round(number, 2), "source": "IMF", "unit": unit, "region": "national",
            "indicator": name if year <= current_year else f"{name} (projection)",
            "url": f"{IMF_URL}/{code}/TCD",
        })
    return records
