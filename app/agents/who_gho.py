"""WHO Global Health Observatory (OData API, no key): official WHO series for Chad.

    GET https://ghoapi.azureedge.net/api/{IndicatorCode}?$filter=SpatialDim eq 'TCD'

Each answer is {"value": [ {TimeDim, NumericValue, Dim1, Dim2, Dim3, DataSourceDim, Date, ...} ]}.
A year can appear several times (by sex, by area, by survey): only the all-population row is kept,
and when several sources give the same year the one without a named source (the WHO estimate),
then the most recently updated, wins.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

GHO_URL = "https://ghoapi.azureedge.net/api"
SOURCE = "WHO GHO"
FIRST_YEAR = 1960

# code -> (indicator name, unit up to 40 characters). Checked against the live API for Chad (Nov 2026).
GHO_INDICATORS: dict[str, tuple[str, str]] = {
    "WHOSIS_000001": ("Life expectancy at birth (WHO)", "years"),
    "WHOSIS_000002": ("Healthy life expectancy at birth (WHO)", "years"),
    "WHOSIS_000004": ("Adult mortality rate (WHO)", "per 1,000 adults 15-60"),
    "MDG_0000000001": ("Infant mortality rate (WHO)", "per 1,000 live births"),
    "MDG_0000000007": ("Under-five mortality rate (WHO)", "per 1,000 live births"),
    "MDG_0000000025": ("Births attended by skilled personnel (WHO)", "% of births"),
    "MDG_0000000026": ("Maternal mortality ratio (WHO)", "per 100,000 live births"),
    "WHS8_110": ("Measles vaccine coverage, first dose (WUENIC)", "% of 1-year-olds"),
    "WHS4_117": ("Hepatitis B vaccine coverage, third dose (WUENIC)", "% of 1-year-olds"),
    "WHS4_543": ("BCG vaccine coverage (WUENIC)", "% of 1-year-olds"),
    "MALARIA_EST_INCIDENCE": ("Estimated malaria incidence (WHO)", "per 1,000 population at risk"),
    "MALARIA_EST_DEATHS": ("Estimated malaria deaths (WHO)", "deaths"),
    "HIV_0000000026": ("New HIV infections (WHO)", "people"),
    "UHC_INDEX_REPORTED": ("UHC service coverage index (WHO)", "index (0-100)"),
    "HWF_0001": ("Medical doctors (WHO)", "per 10,000 people"),
    "HWF_0006": ("Nursing and midwifery personnel (WHO)", "per 10,000 people"),
    "WSH_WATER_BASIC": ("Basic drinking-water services (WHO/UNICEF JMP)", "% of population"),
    "WSH_SANITATION_BASIC": ("Basic sanitation services (WHO/UNICEF JMP)", "% of population"),
    "GHED_CHEGDP_SHA2011": ("Current health expenditure (WHO)", "% of GDP"),
    "GHED_OOPSCHE_SHA2011": ("Out-of-pocket health spending (WHO)", "% of current health expenditure"),
    "RS_198": ("Road traffic death rate (WHO)", "per 100,000 population"),
    "SDGPM25": ("Fine particulate matter PM2.5 (WHO)", "µg/m³"),
    "NCD_BMI_30A": ("Adult obesity, age-standardized (WHO)", "% of adults"),
    "M_Est_smk_curr_std": ("Current tobacco smoking, age-standardized (WHO)", "% of adults"),
    "SA_0000001688": ("Alcohol consumption per adult (WHO)", "litres of pure alcohol"),
}


def _all_population(row: dict[str, Any], strict: bool = True) -> bool:
    """True for the row that covers everybody (no breakdown, or both sexes / total of the area).
    Not strict: a second breakdown (age group, wealth...) is tolerated, for series that only exist with one."""
    if strict and (row.get("Dim2") or row.get("Dim3")):
        return False
    dim1 = row.get("Dim1")
    return dim1 in (None, "") or str(dim1).endswith(("_BTSX", "_TOTL"))


def describe_rows(payload: Any) -> str:
    """Why a series gave nothing, for the run report: how many rows and which breakdowns they carry."""
    rows = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return "no data for Chad"
    seen = {k: sorted({str(r.get(k)) for r in rows if isinstance(r, dict)})[:3] for k in ("Dim1", "Dim2", "Dim3")}
    bad = sum(1 for r in rows if isinstance(r, dict) and not isinstance(r.get("NumericValue"), (int, float)))
    return f"{len(rows)} rows but none usable (no value: {bad}; Dim1 {seen['Dim1']}, Dim2 {seen['Dim2']}, Dim3 {seen['Dim3']})"


def parse_gho(payload: Any, code: str, today: datetime | None = None) -> list[dict[str, Any]]:
    """One record per year for `code`; [] when the answer has not the expected shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), list) or code not in GHO_INDICATORS:
        return []
    name, unit = GHO_INDICATORS[code]
    last_year = (today or datetime.now(UTC)).year
    rows = [r for r in payload["value"] if isinstance(r, dict)]
    strict = any(_all_population(r) for r in rows)      # no clean all-population row at all: accept a second breakdown
    best: dict[int, tuple[tuple[int, str], dict[str, Any]]] = {}
    for row in rows:
        if not _all_population(row, strict):
            continue
        value, year = row.get("NumericValue"), row.get("TimeDim")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(year, int):
            continue
        if year > last_year or year < FIRST_YEAR:  # projections (tobacco to 2030) are not observations; the platform starts in 1960
            continue
        rank = (0 if not row.get("DataSourceDim") else 1, "".join(chr(255 - ord(c)) for c in str(row.get("Date") or "")))
        if year not in best or rank < best[year][0]:
            best[year] = (rank, row)
    return [
        {"year": year, "value": round(float(row["NumericValue"]), 2), "source": SOURCE, "indicator": name,
         "unit": unit, "region": "national", "url": f"{GHO_URL}/{code}"}
        for year, (_, row) in sorted(best.items())
    ]
