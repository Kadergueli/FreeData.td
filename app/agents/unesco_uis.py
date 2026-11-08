"""UNESCO Institute for Statistics (public API, no key): official education series for Chad.

    GET https://api.uis.unesco.org/api/public/data/indicators?indicator={code}&geoUnit=TCD

The country code is ISO3 (TCD): "TD" answers "geoUnit could not be found". An answer is
{"hints": [...], "records": [{"indicatorId", "geoUnit", "year", "value"}, ...]}; an unknown indicator
gives no record and a hint, which the run report shows so the list below can be corrected.
"""
from __future__ import annotations

from typing import Any

UIS_URL = "https://api.uis.unesco.org/api/public/data/indicators"
SOURCE = "UNESCO UIS"
FIRST_YEAR = 1960

# code -> (indicator name, unit). GER.1 and CR.1 are verified for Chad; the other codes follow UIS naming
# and are reported by the run when UIS does not know them.
UIS_INDICATORS: dict[str, tuple[str, str]] = {
    "GER.02": ("Gross enrolment ratio, pre-primary (UIS)", "% of age group"),
    "GER.1": ("Gross enrolment ratio, primary (UIS)", "% of age group"),
    "GER.2": ("Gross enrolment ratio, lower secondary (UIS)", "% of age group"),
    "GER.3": ("Gross enrolment ratio, upper secondary (UIS)", "% of age group"),
    "GER.5T8": ("Gross enrolment ratio, tertiary (UIS)", "% of age group"),
    "CR.1": ("Completion rate, primary (UIS)", "% of age group"),
    "CR.2": ("Completion rate, lower secondary (UIS)", "% of age group"),
    "CR.3": ("Completion rate, upper secondary (UIS)", "% of age group"),
    "ROFST.1.CP": ("Out-of-school rate, primary age (UIS)", "% of age group"),
    "LR.AG15T99": ("Adult literacy rate, 15+ (UIS)", "% of population 15+"),
    "LR.AG15T24": ("Youth literacy rate, 15-24 (UIS)", "% of population 15-24"),
    "XGDP.FSGOV": ("Government expenditure on education (UIS)", "% of GDP"),
    "PTRHC.1": ("Pupil-teacher ratio, primary (UIS)", "pupils per teacher"),
    "PTRHC.2": ("Pupil-teacher ratio, secondary (UIS)", "pupils per teacher"),
}


def parse_uis(payload: Any, code: str) -> list[dict[str, Any]]:
    """One record per year for `code`; [] when the answer has not the expected shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list) or code not in UIS_INDICATORS:
        return []
    name, unit = UIS_INDICATORS[code]
    best: dict[int, float] = {}
    for rec in payload["records"]:
        if not isinstance(rec, dict) or rec.get("indicatorId") != code:
            continue
        value, year = rec.get("value"), rec.get("year")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(year, int) or year < FIRST_YEAR:
            continue
        best[year] = float(value)
    return [{"year": y, "value": round(v, 2), "source": SOURCE, "indicator": name, "unit": unit, "region": "national",
             "url": f"{UIS_URL}?indicator={code}&geoUnit=TCD"} for y, v in sorted(best.items())]


def describe_uis(payload: Any) -> str:
    """Why a series gave nothing: the hint UIS sent, or an empty answer."""
    hints = payload.get("hints") if isinstance(payload, dict) else None
    if isinstance(hints, list) and hints and isinstance(hints[0], dict):
        return str(hints[0].get("message") or "no data")[:80]
    return "no data for Chad"
