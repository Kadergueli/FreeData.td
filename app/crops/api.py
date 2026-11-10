"""API publique d'aptitude culturale : quelle culture convient à quel lieu, quand semer, et pourquoi."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings
from app.crops import explain
from app.crops.calendar import sowing_calendar
from app.crops.engine import assess, load_crops, rank
from app.crops.sites import find_region, region_names, site_for
from app.security import rate_limiter

router = APIRouter(prefix="/api/v1/crops", tags=["crops"])


def _site_or_error(region: str) -> dict[str, Any]:
    name = find_region(region)
    if name is None:
        raise HTTPException(404, f"Unknown region '{region}'. Known: {', '.join(region_names())}")
    data = site_for(name)
    if not data["site"]:
        raise HTTPException(503, "Climate and soil data are not loaded yet")
    return data


def _requirements(crop: dict[str, Any]) -> dict[str, Any]:
    return {k: crop[k] for k in ("rain_mm", "temp_mean_c", "ph", "cycle_days")}


def _public(result: dict[str, Any]) -> dict[str, Any]:
    crop = load_crops()[result["crop"]]
    return {**result, "name_fr": crop["fr"], "name_en": crop["en"], "requirements": _requirements(crop)}


def _calendar(crop_id: str, data: dict[str, Any]) -> list[dict[str, Any]] | None:
    climate = data.get("climate")
    if not climate:
        return None
    return sowing_calendar(load_crops()[crop_id], climate["rain_mm_day"], climate["temp_c"])


def _facts(data: dict[str, Any], crop_id: str, lang: str) -> tuple[dict[str, Any], str, list[dict[str, Any]] | None]:
    """(faits, texte par règles, calendrier) d'une culture sur un lieu."""
    crop = load_crops()[crop_id]
    calendar = _calendar(crop_id, data)
    facts = explain.build_facts(data["region"], crop[lang], assess(crop_id, data["site"]), _requirements(crop), data["site"], calendar, lang)
    return facts, explain.template_summary(facts, lang), calendar


def _crop_or_error(crop: str) -> str:
    if crop not in load_crops():
        raise HTTPException(404, f"Unknown crop '{crop}'. Known: {', '.join(load_crops())}")
    return crop


@router.get("")
def crops() -> dict[str, Any]:
    """Cultures évaluables et lieux disponibles."""
    return {"crops": [{"id": cid, "name_fr": c["fr"], "name_en": c["en"], "scientific_name": c["scientific_name"]}
                      for cid, c in load_crops().items()], "regions": region_names()}


@router.get("/suitability")
def suitability(region: str = Query(..., min_length=2), crop: str | None = Query(None),
                lang: str = Query("fr", pattern="^(fr|en)$")) -> dict[str, Any]:
    """Aptitude d'une culture (`crop`) pour une région, ou de toutes les cultures classées si `crop` est omis.

    Pour une culture : calendrier de semis pluvial (12 mois) et résumé écrit dans la langue `lang`.
    """
    data = _site_or_error(region)
    body: dict[str, Any] = {
        "region": data["region"], "site": data["site"], "missing": data["missing"],
        "method": "FAO EcoCrop requirements; trapezoid score per factor, climate decides (most limiting factor), soil pH lowers the score by at most 40%",
        "sources": ["FAO EcoCrop", "NASA POWER", "SoilGrids (ISRIC)"]}
    if crop is None:
        body["results"] = [_public(r) for r in rank(data["site"])]
        return body
    crop_id = _crop_or_error(crop)
    facts, summary, calendar = _facts(data, crop_id, lang)
    body["results"] = [_public(assess(crop_id, data["site"]))]
    body["calendar"] = calendar
    body["summary"] = summary
    return body


@router.post("/explain")
async def explain_note(request: Request, region: str = Query(..., min_length=2), crop: str = Query(...),
                       lang: str = Query("fr", pattern="^(fr|en)$")) -> dict[str, Any]:
    """Note rédigée par l'IA à partir des seuls chiffres calculés ; texte par règles si l'IA est indisponible.

    Réponse : text, source ("ai" ou "template"), model, reason (pourquoi le texte par règles, le cas échéant).
    Le texte de l'IA est refusé s'il cite un chiffre qui n'est pas dans les faits. Les réponses sont mises en cache.
    """
    data = _site_or_error(region)
    crop_id = _crop_or_error(crop)
    key = (data["region"], crop_id, lang)
    cached = explain.cache_get(key)
    if cached:
        return cached
    facts, baseline, _ = _facts(data, crop_id, lang)
    client = request.client.host if request.client else "unknown"
    if not settings.groq_api_key:
        text, reason = None, "no-key"
    elif not rate_limiter.allow(f"crops-ai:{client}", settings.crops_ai_rate_limit_per_hour) or \
            not rate_limiter.allow("crops-ai:*global*", settings.crops_ai_global_limit_per_hour):
        text, reason = None, "rate-limited"
    else:
        text, reason = await explain.ai_note(facts, baseline, lang)
    if text:
        out = {"text": text, "source": "ai", "model": reason, "lang": lang}
        explain.cache_set(key, out)  # seule une vraie rédaction IA est mise en cache : un échec doit pouvoir être retenté
        return out
    return {"text": baseline, "source": "template", "model": None, "reason": reason, "lang": lang}
