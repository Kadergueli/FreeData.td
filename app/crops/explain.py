"""Explication d'un résultat d'aptitude, en français ou en anglais.

`template_summary` : texte professionnel construit par règles à partir des chiffres du résultat. Toujours
disponible, sans IA, entièrement vérifiable. `ai_note` : le même contenu reformulé par un modèle de langage,
qui ne reçoit que ces faits ; si son texte contient un chiffre qui n'est pas dans les faits, il est rejeté et
le texte par règles est servi. Le cache évite de payer deux fois la même question (les données sont fixes).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import settings
from app.crops.calendar import good_months, runs

logger = logging.getLogger(__name__)

LANGS = ("fr", "en")
MONTH_NAMES = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}
VERDICT = {
    "fr": {"very_suitable": "très adapté", "suitable": "adapté", "marginal": "marginal", "unsuitable": "non adapté", "unknown": "indéterminé"},
    "en": {"very_suitable": "very suitable", "suitable": "suitable", "marginal": "marginal", "unsuitable": "unsuitable", "unknown": "undetermined"},
}
FACTOR = {
    "fr": {"rain_mm": "la pluie de la saison", "temp_mean_c": "la température de la saison", "season_days": "la durée de la saison des pluies", "ph": "le pH du sol"},
    "en": {"rain_mm": "seasonal rainfall", "temp_mean_c": "seasonal temperature", "season_days": "rainy-season length", "ph": "soil pH"},
}
UNIT = {"rain_mm": "mm", "temp_mean_c": "°C", "season_days": {"fr": "jours", "en": "days"}, "ph": ""}


def _unit(factor: str, lang: str) -> str:
    u = UNIT[factor]
    return u[lang] if isinstance(u, dict) else u


def _n(x: float, lang: str = "en") -> str:
    """Nombre sans zéros inutiles, virgule décimale en français : 991.0 -> 991, 6.08 -> 6,08."""
    text = str(int(x)) if float(x) == int(x) else str(round(float(x), 2)).rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "fr" else text


def _period(a: int, b: int, lang: str) -> str:
    names = MONTH_NAMES[lang]
    if a == b:
        return names[a - 1]
    return f"{names[a - 1]} {'à' if lang == 'fr' else 'to'} {names[b - 1]}"


def sowing_periods(calendar: list[dict[str, Any]] | None, lang: str) -> list[str]:
    return [_period(a, b, lang) for a, b in runs(good_months(calendar or []))]


def build_facts(region: str, crop_name: str, result: dict[str, Any], requirements: dict[str, Any],
                site: dict[str, Any], calendar: list[dict[str, Any]] | None, lang: str) -> dict[str, Any]:
    """Ce que le texte a le droit de dire : uniquement des valeurs calculées, jamais d'estimation du modèle."""
    factors = {}
    for f, fa in result.get("factors", {}).items():
        req = requirements.get(f) if f != "season_days" else None
        factors[f] = {"value": fa["value"], "score_pct": round(fa["score"] * 100),
                      "optimum": [req[1], req[2]] if req else None,
                      "needs_days": requirements["cycle_days"][0] if f == "season_days" else None}
    irr = result.get("if_irrigated")
    return {
        "region": region, "crop": crop_name, "verdict": result["verdict"], "score_pct": round((result["score"] or 0) * 100),
        "limiting": result.get("limiting"), "factors": factors,
        "if_irrigated": {"score_pct": round(irr["score"] * 100), "verdict": irr["verdict"]} if irr else None,
        "sowing": sowing_periods(calendar, lang) if calendar is not None else None,
    }


def template_summary(facts: dict[str, Any], lang: str) -> str:
    """Texte professionnel par règles, dans la langue demandée."""
    fr = lang == "fr"
    v = VERDICT[lang][facts["verdict"]]
    parts: list[str] = []
    if facts["verdict"] == "unknown":
        return (f"Les données climatiques ou pédologiques de {facts['region']} ne permettent pas d'évaluer {facts['crop']}."
                if fr else f"The climate or soil data for {facts['region']} do not allow {facts['crop']} to be assessed.")
    parts.append(f"{facts['crop']} à {facts['region']} : verdict {v} ({facts['score_pct']} %)." if fr
                 else f"{facts['crop']} in {facts['region']}: {v} ({facts['score_pct']}%).")
    lim = facts["limiting"]
    if lim and lim in facts["factors"]:
        fa = facts["factors"][lim]
        unit = _unit(lim, lang)
        sp = f" {unit}" if unit else ""
        if facts["verdict"] in ("very_suitable", "suitable") and fa["score_pct"] >= 95:
            parts.append("Le climat répond aux besoins de la culture." if fr else "The climate meets the crop's needs.")
        elif lim == "season_days":
            parts.append(f"La saison des pluies dure {_n(fa['value'], lang)} jours, pour un cycle d'au moins {_n(fa['needs_days'], lang)} jours." if fr
                         else f"The rainy season lasts {_n(fa['value'], lang)} days, for a cycle of at least {_n(fa['needs_days'], lang)} days.")
        elif fa["optimum"]:
            lo, hi = _n(fa["optimum"][0], lang), _n(fa["optimum"][1], lang)
            parts.append(f"Le facteur limitant est {FACTOR[lang][lim]} : {_n(fa['value'], lang)}{sp} pour un optimum de {lo} à {hi}{sp}." if fr
                         else f"The limiting factor is {FACTOR[lang][lim]}: {_n(fa['value'], lang)}{sp} against an optimum of {lo} to {hi}{sp}.")
    ph = facts["factors"].get("ph")
    if ph and ph["score_pct"] < 100 and ph["optimum"]:
        lo, hi = _n(ph["optimum"][0], lang), _n(ph["optimum"][1], lang)
        parts.append(f"Le pH du sol ({_n(ph['value'], lang)}) est hors de l'optimum ({lo} à {hi}) : il réduit le score sans l'annuler, et peut se corriger par amendement." if fr
                     else f"Soil pH ({_n(ph['value'], lang)}) is outside the optimum ({lo} to {hi}): it lowers the score without cancelling it, and can be corrected with amendments.")
    irr = facts.get("if_irrigated")
    if irr:
        parts.append(f"Avec irrigation ou en plaine inondable, l'aptitude passe à {irr['score_pct']} % ({VERDICT[lang][irr['verdict']]}), à condition que l'eau soit disponible." if fr
                     else f"With irrigation or on a flood plain, suitability rises to {irr['score_pct']}% ({VERDICT[lang][irr['verdict']]}), provided water is available.")
    if facts.get("sowing") is not None:
        if facts["sowing"]:
            when = (" et " if fr else " and ").join(facts["sowing"])
            parts.append(f"Période de semis pluvial favorable : {when}." if fr else f"Favourable rainfed sowing period: {when}.")
        else:
            parts.append("Aucun mois ne permet un semis pluvial favorable." if fr else "No month allows a favourable rainfed sowing.")
    parts.append("Indicatif : valeurs moyennes à un point par région, à confirmer avec un conseiller agricole." if fr
                 else "Indicative: average values at one point per region, to be confirmed with an agricultural adviser.")
    return " ".join(parts)


# Le modèle ne calcule ni rendement, ni prix, ni quantité : un texte qui en parle invente.
FORBIDDEN = re.compile(r"\b(tonnes?|tons?|kg|kilos?|hectares?|ha|rendements?|yields?|fcfa|xaf|usd|euros?|dollars?|prix|price|revenus?|profit)\b|[€$]",
                       re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> set[float]:
    return {float(m.replace(",", ".")) for m in NUMBER.findall(text)}


def allowed_numbers(facts: dict[str, Any], baseline: str) -> set[float]:
    """Les chiffres que le texte peut citer : ceux des faits et du texte par règles."""
    return numbers_in(json.dumps(facts, ensure_ascii=False)) | numbers_in(baseline)


_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def cache_get(key: tuple[str, str, str]) -> dict[str, Any] | None:
    return _CACHE.get(key)


def cache_set(key: tuple[str, str, str], value: dict[str, Any]) -> None:
    if len(_CACHE) >= 500:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value


def _prompt(facts: dict[str, Any], baseline: str, lang: str) -> tuple[str, str]:
    language = "français" if lang == "fr" else "English"
    system = (f"Tu es l'agronome de FreeData.td. Tu rédiges en {language}, de façon professionnelle, claire et neutre, pour des agriculteurs, "
              "techniciens et décideurs. Tu n'utilises QUE les faits fournis : aucun autre chiffre, aucune variété, aucun rendement, "
              "aucun produit, aucune prévision. Pas de préambule ni de méta-commentaire. 90 mots maximum, un seul paragraphe, "
              "sans titre ni liste. Tu gardes les nuances et les limites des faits.") if lang == "fr" else (
        "You are FreeData.td's agronomist. You write in English, professionally, clearly and neutrally, for farmers, technicians and "
        "decision-makers. You use ONLY the facts given: no other number, no variety, no yield, no product, no forecast. No preamble or "
        "meta-commentary. At most 90 words, one paragraph, no heading or list. Keep the nuances and limits of the facts.")
    user = f"Faits (JSON) :\n{json.dumps(facts, ensure_ascii=False)}\n\nTexte de référence à reformuler :\n{baseline}"
    return system, user


async def ai_note(facts: dict[str, Any], baseline: str, lang: str) -> tuple[str | None, str]:
    """(texte, modèle) rédigé par l'IA, ou (None, raison) si indisponible, rejeté ou sans clé."""
    if not settings.groq_api_key:
        return None, "no-key"
    system, user = _prompt(facts, baseline, lang)
    allowed = allowed_numbers(facts, baseline)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions",
                                     headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                                     json={"model": settings.groq_model, "temperature": 0.2, "max_tokens": 350,
                                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        if resp.status_code != 200:
            return None, f"http-{resp.status_code}"
        text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:  # réseau, JSON : jamais bloquant, le texte par règles prend le relais
        logger.warning("crop explanation model failed: %s", exc)
        return None, "error"
    if not text:
        return None, "empty"
    if FORBIDDEN.search(text):
        logger.info("crop explanation rejected: it talks about yield, quantity or price")
        return None, "rejected"
    if numbers_in(text) - allowed:
        logger.info("crop explanation rejected: numbers outside the facts: %s", sorted(numbers_in(text) - allowed))
        return None, "rejected"
    return text, settings.groq_model
