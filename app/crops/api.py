"""API publique d'aptitude culturale : quelle culture convient à quel lieu."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.crops.engine import assess, load_crops, rank
from app.crops.sites import find_region, region_names, site_for

router = APIRouter(prefix="/api/v1/crops", tags=["crops"])


def _site_or_error(region: str) -> dict[str, Any]:
    name = find_region(region)
    if name is None:
        raise HTTPException(404, f"Unknown region '{region}'. Known: {', '.join(region_names())}")
    data = site_for(name)
    if not data["site"]:
        raise HTTPException(503, "Climate and soil data are not loaded yet")
    return data


def _public(result: dict[str, Any]) -> dict[str, Any]:
    crop = load_crops()[result["crop"]]
    return {**result, "name_fr": crop["fr"], "name_en": crop["en"]}


@router.get("")
def crops() -> dict[str, Any]:
    """Cultures évaluables et lieux disponibles."""
    return {"crops": [{"id": cid, "name_fr": c["fr"], "name_en": c["en"], "scientific_name": c["scientific_name"]}
                      for cid, c in load_crops().items()], "regions": region_names()}


@router.get("/suitability")
def suitability(
    region: str = Query(..., min_length=2, max_length=100),
    crop: str | None = Query(None, max_length=40),
) -> dict[str, Any]:
    """Aptitude d'une culture (`crop`) pour une région, ou de toutes les cultures classées si `crop` est omis."""
    data = _site_or_error(region)
    if crop is not None and crop not in load_crops():
        raise HTTPException(404, f"Unknown crop '{crop}'. Known: {', '.join(load_crops())}")
    results = [assess(crop, data["site"])] if crop else rank(data["site"])
    return {"region": data["region"], "site": data["site"], "missing": data["missing"],
            "method": "FAO EcoCrop requirements; trapezoid score per factor, the most limiting factor decides",
            "sources": ["FAO EcoCrop", "NASA POWER", "SoilGrids (ISRIC)"],
            "results": [_public(r) for r in results]}
