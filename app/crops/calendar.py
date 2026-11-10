"""Calendrier de semis pluvial d'une culture : pour chaque mois de semis, le climat du cycle qui suit.

Pour un semis au début du mois m, on regarde les n mois suivants (n = durée typique du cycle, en mois) :
cumul de pluie et température moyenne, comparés aux besoins de la culture (mêmes trapèzes que l'aptitude).
Le semis exige aussi un mois de départ assez humide pour faire lever la graine. Climat seulement : le sol
est le même toute l'année. Fonction pure.
"""
from __future__ import annotations

from typing import Any

from app.crops.engine import trapezoid, verdict_for
from app.crops.profile import DAYS, MONTHS

GERMINATION_MM = 20  # pluie minimale du mois de semis


def cycle_months(crop: dict[str, Any]) -> int:
    """Durée typique du cycle en mois : la moitié de la fourchette EcoCrop, au moins un mois."""
    low, high = crop["cycle_days"]
    return max(1, round((low + high) / 2 / 30.4))


def sowing_calendar(crop: dict[str, Any], rain_mm_day: dict[str, float], temp_c: dict[str, float]) -> list[dict[str, Any]]:
    """Douze entrées {month (1-12), score, verdict, cycle_end}, verdict comme pour l'aptitude (très adapté… non adapté)."""
    rain = [float(rain_mm_day[m]) * DAYS[i] for i, m in enumerate(MONTHS)]
    temp = [float(temp_c[m]) for m in MONTHS]
    n = cycle_months(crop)
    out: list[dict[str, Any]] = []
    for start in range(12):
        window = [(start + k) % 12 for k in range(n)]
        rain_score = trapezoid(sum(rain[i] for i in window), *crop["rain_mm"])
        temp_score = trapezoid(sum(temp[i] for i in window) / n, *crop["temp_mean_c"])
        score = 0.0 if rain[start] < GERMINATION_MM else min(rain_score, temp_score)
        out.append({"month": start + 1, "score": round(score, 3), "verdict": verdict_for(score),
                    "cycle_end": window[-1] + 1})
    return out


def good_months(calendar: list[dict[str, Any]]) -> list[int]:
    """Mois de semis recommandés (adapté ou très adapté), dans l'ordre du calendrier."""
    return [c["month"] for c in calendar if c["verdict"] in ("suitable", "very_suitable")]


def runs(months: list[int]) -> list[tuple[int, int]]:
    """Regroupe des mois en périodes continues (circulaires : décembre-janvier ne font qu'une période)."""
    if not months:
        return []
    ms = sorted(set(months))
    if len(ms) == 12:
        return [(1, 12)]
    groups: list[list[int]] = [[ms[0]]]
    for m in ms[1:]:
        if m == groups[-1][-1] + 1:
            groups[-1].append(m)
        else:
            groups.append([m])
    if len(groups) > 1 and groups[0][0] == 1 and groups[-1][-1] == 12:
        groups[0] = groups.pop() + groups[0]
    return [(g[0], g[-1]) for g in groups]
