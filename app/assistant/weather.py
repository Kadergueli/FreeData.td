"""Lens « météo » : températures et pluie par province (archives Open-Meteo, mesures quotidiennes).

Ce sont des MESURES passées (avec quelques jours de retard), pas des prévisions : la lens le dit
quand on lui demande « demain » ou « cette semaine ».
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.assistant.text import find_alias, fmt_day, fmt_number, normalize, parse_date
from app.regions import PROVINCES, canonical_province

DISPLAY_PROVINCE = {"Guera": "Guéra", "Ouaddai": "Ouaddaï", "Tandjile": "Tandjilé"}

# Chef-lieu (ou grande ville) -> province, pour que « Moundou » ou « Abéché » suffisent.
CITY_TO_PROVINCE = {
    "abeche": "Ouaddai", "moundou": "Logone Occidental", "sarh": "Moyen-Chari", "bol": "Lac",
    "mongo": "Guera", "faya": "Borkou", "faya largeau": "Borkou", "am timan": "Salamat",
    "doba": "Logone Oriental", "bongor": "Mayo-Kebbi Est", "pala": "Mayo-Kebbi Ouest",
    "lai": "Tandjile", "koumra": "Mandoul", "ati": "Batha", "biltine": "Wadi Fira",
    "fada": "Ennedi Ouest", "am djarass": "Ennedi Est", "amdjarass": "Ennedi Est", "mao": "Kanem",
    "massakory": "Hadjer-Lamis", "massenya": "Chari-Baguirmi", "goz beida": "Sila",
    "moussoro": "Barh el Gazel", "bardai": "Tibesti", "adre": "Ouaddai", "oum hadjer": "Batha",
}

# Questions : mots qui annoncent la météo.
TEMPERATURE_WORDS = ("temperature", "temperatures", "chaud", "chaude", "chaleur", "froid", "frais", "degre", "degres")
RAIN_WORDS = ("pluie", "pluies", "pleut", "pleuvoir", "pleuvra", "pluvieux", "pluviometrie", "precipitation", "precipitations", "averse", "averses", "arrose")
GENERAL_WORDS = ("meteo", "temps qu'il fait", "quel temps", "climat", "il fait")
FORECAST_WORDS = ("demain", "apres demain", "previsions", "prevision", "prevoir", "va faire", "va pleuvoir",
                  "prochain", "prochaine", "prochains", "prochaines", "week end", "weekend")
MONTH_WORDS = ("mois", "30 jours", "trente jours")


def _province_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in PROVINCES:
        n = normalize(p)
        out[n] = p
        out[n.replace("'", "")] = p
        out[n.replace("'", " ")] = p
        out[n.replace(" ", "")] = p
    out.update({"barh el gazal": "Barh el Gazel", "bahr el gazal": "Barh el Gazel"})
    out.update(CITY_TO_PROVINCE)
    return out


_ALIASES = _province_aliases()


PROVINCE_NAMES = frozenset(PROVINCES)


def all_aliases() -> list[str]:
    return list(_ALIASES.keys())


def find_province(norm_text: str) -> tuple[str, str] | None:
    """(province canonique, mot cité) ; l'alias le plus long gagne (« mayo kebbi est » > « est »)."""
    best: tuple[int, int, str, str] | None = None
    for alias, province in _ALIASES.items():
        span = find_alias(norm_text, alias)
        if span:
            key = (-len(alias), span[0], province, alias)
            if best is None or key < best:
                best = key
    return (best[2], best[3]) if best else None


def mentions_weather(norm_text: str) -> bool:
    return any(find_alias(norm_text, w) for w in TEMPERATURE_WORDS + RAIN_WORDS + GENERAL_WORDS)


def wants_forecast(norm_text: str) -> bool:
    return any(find_alias(norm_text, w) for w in FORECAST_WORDS)


def wants_month(norm_text: str) -> bool:
    return any(find_alias(norm_text, w) for w in MONTH_WORDS)


def wants(norm_text: str) -> tuple[bool, bool]:
    """(température demandée, pluie demandée). Question générale (« météo ») : les deux."""
    temp = any(find_alias(norm_text, w) for w in TEMPERATURE_WORDS)
    rain = any(find_alias(norm_text, w) for w in RAIN_WORDS)
    if not temp and not rain:
        return True, True
    return temp, rain


@dataclass(frozen=True)
class Measure:
    province: str
    date: str
    value: float
    unit: str
    source: str


def region_province(region: str) -> str | None:
    """Province of a stored region: 'Abeche (Ouaddai)' -> 'Ouaddai', 'Ouaddai' -> 'Ouaddai'."""
    text = region or ""
    m = re.match(r"^.*\(([^()]*)\)\s*$", text)
    return canonical_province(m.group(1)) if m and canonical_province(m.group(1)) else canonical_province(text)


def _series(repo, province: str, indicator: str, limit: int = 40) -> list[Measure]:
    # une seule requête « Daily » (température moyenne/min/max + pluie) partagée via le cache du dépôt
    rows = repo.list_observations(sector="environment", region=province, limit=limit * 5, q="Daily")
    out: dict[str, Measure] = {}
    for r in rows:
        if r.get("indicator") != indicator or region_province(r.get("region") or "") != province:
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError, KeyError):
            continue
        d = str(r.get("reference_date"))[:10]
        out.setdefault(d, Measure(province, d, value, r.get("unit") or "", r.get("source") or ""))
    return sorted(out.values(), key=lambda m: m.date, reverse=True)


def temperature_series(repo, province: str, kind: str = "mean") -> list[Measure]:
    return _series(repo, province, f"Daily {kind} temperature")


def rain_series(repo, province: str) -> list[Measure]:
    return _series(repo, province, "Daily precipitation")


def window_average(series: list[Measure], days: int) -> float | None:
    """Moyenne des mesures des `days` derniers jours CONNUS (à partir de la plus récente)."""
    if not series:
        return None
    last = parse_date(series[0].date)
    vals = [m.value for m in series if (last - parse_date(m.date)).days < days]
    return sum(vals) / len(vals) if vals else None


def window_sum(series: list[Measure], days: int) -> tuple[float, int] | None:
    if not series:
        return None
    last = parse_date(series[0].date)
    vals = [m.value for m in series if (last - parse_date(m.date)).days < days]
    return (sum(vals), len(vals)) if vals else None


def province_label(province: str) -> str:
    return DISPLAY_PROVINCE.get(province, province)


def _stale(d: str, today: date) -> str:
    dd = parse_date(d)
    if dd and (today - dd).days > 14:
        return f" ⚠️ Cette mesure a {(today - dd).days} jours."
    return ""


def describe_temperature(repo, province: str, label: str, today: date, window: int) -> tuple[str, dict] | None:
    mean = temperature_series(repo, province, "mean")
    if not mean:
        return None
    tmin, tmax = temperature_series(repo, province, "min"), temperature_series(repo, province, "max")
    latest = mean[0]
    same_day = lambda s: next((m for m in s if m.date == latest.date), None)   # noqa: E731
    lo, hi = same_day(tmin), same_day(tmax)
    parts = [f"Température à {label} (province : {province_label(province)}), {fmt_day(latest.date)} : "
             f"{fmt_number(latest.value)} °C en moyenne"]
    if lo and hi:
        parts.append(f" (minimum {fmt_number(lo.value)} °C, maximum {fmt_number(hi.value)} °C)")
    avg = window_average(mean, window)
    text = "".join(parts) + "."
    if avg is not None and len(mean) > 1:
        text += f" Moyenne des {window} derniers jours : {fmt_number(avg)} °C."
    text += f" Source : {latest.source}.{_stale(latest.date, today)}"
    return text, {"date": latest.date, "mean": latest.value, "min": lo.value if lo else None,
                  "max": hi.value if hi else None, "window_days": window, "window_mean": avg}


def describe_rain(repo, province: str, label: str, today: date, window: int) -> tuple[str, dict] | None:
    rain = rain_series(repo, province)
    if not rain:
        return None
    latest = rain[0]
    total = window_sum(rain, window)
    text = (f"Pluie à {label} (province : {province_label(province)}), {fmt_day(latest.date)} : "
            f"{fmt_number(latest.value)} mm.")
    if total and total[1] > 1:
        text += f" Cumul sur les {window} derniers jours : {fmt_number(total[0])} mm."
    text += f" Source : {latest.source}.{_stale(latest.date, today)}"
    return text, {"date": latest.date, "mm": latest.value, "window_days": window,
                  "window_total": total[0] if total else None}
