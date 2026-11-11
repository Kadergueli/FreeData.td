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

# code -> (indicator name, unit). Verified by a real run for Chad (Nov 2026). Unknown codes (GER.02,
# PTRHC.1, PTRHC.2) were removed; a code UIS does not know is reported by the run.
UIS_INDICATORS: dict[str, tuple[str, str]] = {
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
    # Codes confirmed on the live UIS API for Chad (rows available: GER.1.GPIA 46, FTP.1 33, FTP.2T3 23, QUALIFIED 7, TRAINED 5).
    "GER.1.GPIA": ("Gender parity index of the gross enrolment ratio, primary (UIS)", "ratio"),
    "FTP.1": ("Female teachers in primary education (UIS)", "% of teachers"),
    "FTP.2T3": ("Female teachers in secondary education (UIS)", "% of teachers"),
    "FTP.1.QUALIFIED": ("Primary teachers qualified to national standards (UIS)", "% of teachers"),
    "FTP.1.TRAINED": ("Primary teachers trained to national standards (UIS)", "% of teachers"),
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
