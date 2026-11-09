"""Profil d'un lieu pour l'aptitude culturale : de la climatologie mensuelle aux valeurs que le moteur compare.

Les besoins EcoCrop portent sur le cycle de la culture, pas sur l'année : on calcule donc la pluie et la température
de la saison des pluies. Fonction pure, sans fichier ni réseau.
"""
from __future__ import annotations

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
DAYS = (31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
WET_MONTH_MM = 50  # un mois est « humide » à partir de 50 mm de pluie


def build_profile(rain_mm_day: dict[str, float], temp_c: dict[str, float]) -> dict[str, float]:
    """Saison des pluies d'un lieu à partir de ses 12 moyennes mensuelles (pluie en mm/jour, température en °C).

    Renvoie rain_mm (cumul de la saison), temp_mean_c (moyenne de la saison), season_days (durée de la saison),
    annual_rain_mm, wet_months. Sans aucun mois humide (désert), la saison est vide : season_days = 0 et la pluie
    comme la température sont celles de l'année entière.
    """
    monthly = [float(rain_mm_day[m]) * DAYS[i] for i, m in enumerate(MONTHS)]
    temps = [float(temp_c[m]) for m in MONTHS]
    wet = [i for i, mm in enumerate(monthly) if mm >= WET_MONTH_MM]
    annual = sum(monthly)
    if wet:
        rain = sum(monthly[i] for i in wet)
        temp = sum(temps[i] for i in wet) / len(wet)
        days = sum(DAYS[i] for i in wet)
    else:
        rain, temp, days = annual, sum(temps) / 12, 0.0
    return {"rain_mm": round(rain, 1), "temp_mean_c": round(temp, 2), "season_days": round(days),
            "annual_rain_mm": round(annual, 1), "wet_months": [MONTHS[i] for i in wet]}
