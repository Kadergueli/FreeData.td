"""Aptitude culturale : compare les besoins d'une culture aux conditions d'un lieu.

Méthode FAO (EcoCrop) : chaque facteur donne un score 0..1 par trapèze. Parmi les facteurs de
climat (pluie, température, durée de saison), le plus limitant décide (loi du minimum, Liebig) ;
le pH du sol retire ensuite au plus 40 % du score.
Fonction pure : aucune base de données ni réseau, donc testable seule.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REQUIREMENTS_FILE = Path(__file__).with_name("requirements.json")

# facteur du site -> clé de la table des besoins
FACTORS = {"rain_mm": "rain_mm", "temp_mean_c": "temp_mean_c", "ph": "ph"}
# Facteur facultatif : la saison des pluies doit couvrir le cycle de la culture (min de cycle_days).
# Compté seulement quand le lieu le fournit ; ne change pas `confidence`, calculée sur FACTORS.
SEASON = "season_days"
WATER_FACTORS = frozenset({"rain_mm", SEASON})  # ce que l'irrigation ou une crue peut remplacer
# Le pH du sol (une valeur par région, modifiable par amendement) retire au plus 40 % du score climatique.
# Choix de modélisation de FreeData.td, pas une règle FAO : à calibrer avec des rendements réels.
SOIL_MAX_PENALTY = 0.4

# (seuil minimum du score global, verdict), du meilleur au pire
VERDICTS = [(0.8, "very_suitable"), (0.6, "suitable"), (0.4, "marginal"), (0.0, "unsuitable")]


@lru_cache(maxsize=1)
def load_crops() -> dict[str, dict[str, Any]]:
    return json.loads(REQUIREMENTS_FILE.read_text(encoding="utf-8"))["crops"]


def trapezoid(x: float, abs_min: float, opt_min: float, opt_max: float, abs_max: float) -> float:
    """1 dans l'optimum, 0 hors des limites absolues, linéaire entre les deux."""
    if x <= abs_min or x >= abs_max:
        return 0.0
    if opt_min <= x <= opt_max:
        return 1.0
    if x < opt_min:
        return (x - abs_min) / (opt_min - abs_min)
    return (abs_max - x) / (abs_max - opt_max)


def verdict_for(score: float) -> str:
    for threshold, name in VERDICTS:
        if score >= threshold:
            return name
    return "unsuitable"


def _assess(crop_id: str, site: dict[str, float | None], skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Évalue une culture sur un site : le climat décide (facteur le plus limitant), le sol module.

    `site` contient les facteurs connus (rain_mm, temp_mean_c, ph). Un facteur
    absent ou None est ignoré et listé dans `unknown` : on ne devine jamais.
    """
    crops = load_crops()
    if crop_id not in crops:
        raise KeyError(f"unknown crop: {crop_id}")
    crop = crops[crop_id]

    factors: dict[str, dict[str, float]] = {}
    unknown: list[str] = []
    for factor, key in FACTORS.items():
        if factor in skip:
            continue
        value = site.get(factor)
        if value is None:
            unknown.append(factor)
            continue
        factors[factor] = {"value": float(value), "score": round(trapezoid(float(value), *crop[key]), 3)}

    if SEASON not in skip and site.get(SEASON) is not None:
        factors[SEASON] = {"value": float(site[SEASON]),
                           "score": round(min(1.0, float(site[SEASON]) / crop["cycle_days"][0]), 3)}

    if not factors:
        return {"crop": crop_id, "score": None, "verdict": "unknown", "limiting": None,
                "factors": {}, "unknown": unknown, "confidence": 0.0, "verified": crop["verified"]}

    core = [f for f in factors if f != "ph"]  # climat : pluie, température, saison
    if not core:
        return {"crop": crop_id, "score": None, "verdict": "unknown", "limiting": None, "factors": factors,
                "unknown": unknown, "confidence": 0.0, "verified": crop["verified"]}
    limiting = min(core, key=lambda f: factors[f]["score"])
    climate_score = factors[limiting]["score"]
    # Le sol module le résultat sans le bloquer : un pH hors optimum retire au plus SOIL_MAX_PENALTY du score.
    ph_score = factors["ph"]["score"] if "ph" in factors else 1.0
    score = round(climate_score * (1 - SOIL_MAX_PENALTY * (1 - ph_score)), 3)
    return {
        "crop": crop_id,
        "score": score,
        "climate_score": climate_score,
        "verdict": verdict_for(score),
        "limiting": limiting,
        "factors": factors,
        "unknown": unknown,
        "confidence": round(min(1.0, len([f for f in factors if f in FACTORS]) / len(FACTORS)), 2),
        "verified": crop["verified"],
    }


def assess(crop_id: str, site: dict[str, float | None]) -> dict[str, Any]:
    """Évalue une culture en pluvial, et ajoute `if_irrigated` quand l'eau de pluie est ce qui la limite.

    Le résultat pluvial suppose que la pluie locale est la seule eau. Le riz de plaine inondable ou de périmètre
    irrigué reçoit de l'eau d'ailleurs : `if_irrigated` donne le même calcul sans le facteur eau (pluie et
    durée de saison), le reste (température, sol) restant en jeu. Il ne dit pas que l'eau est disponible.
    """
    result = _assess(crop_id, site)
    if result["limiting"] in WATER_FACTORS:
        wet = _assess(crop_id, site, skip=WATER_FACTORS)
        if wet["score"] is not None and wet["score"] > (result["score"] or 0):
            result["if_irrigated"] = {"score": wet["score"], "verdict": wet["verdict"], "limiting": wet["limiting"]}
    return result


def rank(site: dict[str, float | None]) -> list[dict[str, Any]]:
    """Toutes les cultures classées de la plus adaptée à la moins adaptée."""
    results = [assess(cid, site) for cid in load_crops()]
    return sorted(results, key=lambda r: (r["score"] is None, -(r["score"] or 0)))
