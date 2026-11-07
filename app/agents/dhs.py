"""DHS Program (Demographic and Health Surveys) aggregated indicators for Chad, national and by region.

    GET https://api.dhsprogram.com/rest/dhs/data?countryIds=TD&indicatorIds=...&breakdown=subnational

No key. Chad has three DHS surveys (1996-97, 2004, 2014-15). Rows carry Indicator, IndicatorId, Value,
SurveyYear, CharacteristicCategory ("Region" or "Total"), CharacteristicLabel ("Logone Occidental 2014")
and ByVariableId (0 when the row is not broken down by another variable).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

DHS_URL = "https://api.dhsprogram.com/rest/dhs/data"
SOURCE = "DHS Program"
PAGE = 5000
MAX_PAGES = 10

# indicator id -> unit (the name comes with the answer). An id the API does not know simply returns no row.
DHS_INDICATORS: dict[str, str] = {
    "CM_ECMR_C_U5M": "per 1,000 live births",
    "CM_ECMR_C_IMR": "per 1,000 live births",
    "CM_ECMR_C_NNR": "per 1,000 live births",
    "FE_FRTR_W_TFR": "children per woman",
    "RH_ANCN_W_N4P": "% of women",
    "RH_DELP_C_DHF": "% of births",
    "RH_DELA_C_SKP": "% of births",
    "CH_VACC_C_BAS": "% of children 12-23 months",
    "CH_VACC_C_MSL": "% of children 12-23 months",
    "CH_VACC_C_DP3": "% of children 12-23 months",
    "CN_NUTS_C_HA2": "% of children under 5",
    "CN_NUTS_C_WH2": "% of children under 5",
    "CN_NUTS_C_WA2": "% of children under 5",
    "CH_DIAR_C_DIA": "% of children under 5",
    "ML_NETP_H_ITN": "% of households",
    "ML_NETU_C_ITN": "% of children under 5",
    "FP_CUSA_W_MOD": "% of women",
    "FP_NADM_W_UNT": "% of women",
    "HA_HIVP_B_HIV": "% of adults 15-49",
    "ED_EDUC_W_NED": "% of women",
    "ED_EDUC_M_NED": "% of men",
    "ED_LITR_W_LIT": "% of women",
    "ED_LITR_M_LIT": "% of men",
    "ED_NARP_B_BTH": "% of children",
    "ED_NARS_B_BTH": "% of adolescents",
    "WS_SRCE_P_BAS": "% of population",
    "WS_TLET_P_BAS": "% of population",
    "HC_ELEC_P_ELC": "% of households",
}


def clean_region(label: str) -> str:
    """"Logone Occidental 2014" -> "Logone Occidental"; "N'Djaména 1997" -> "N'Djamena" (no accents,
    like the region names already stored)."""
    text = re.sub(r"\s*\(?\b(19|20)\d{2}(-\d{2,4})?\)?\s*$", "", str(label)).strip()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return text or "national"


def parse_dhs(payload: Any) -> list[dict[str, Any]]:
    """Records from one page: all-population rows only, one per (indicator, year, region)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("Data"), list):
        return []
    best: dict[tuple[str, int, str], tuple[int, dict[str, Any]]] = {}
    for row in payload["Data"]:
        if not isinstance(row, dict) or str(row.get("ByVariableId", 0)) not in ("0", ""):
            continue
        ind_id, value, year = row.get("IndicatorId"), row.get("Value"), row.get("SurveyYear")
        if ind_id not in DHS_INDICATORS or not isinstance(year, int):
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        category = str(row.get("CharacteristicCategory", ""))
        if category == "Region":
            region = clean_region(row.get("CharacteristicLabel", ""))
        elif category == "Total" or row.get("IsTotal") in (1, "1"):
            region = "national"
        else:
            continue
        key = (str(ind_id), year, region)
        rank = 0 if row.get("IsPreferred") in (1, "1") else 1
        if key not in best or rank < best[key][0]:
            best[key] = (rank, row)
    return [
        {"year": year, "value": round(float(row["Value"]), 2), "source": SOURCE,
         "indicator": str(row.get("Indicator", ind_id)).strip(), "unit": DHS_INDICATORS[ind_id],
         "region": region, "url": f"{DHS_URL}?countryIds=TD&indicatorIds={ind_id}"}
        for (ind_id, year, region), (_, row) in sorted(best.items())
    ]
