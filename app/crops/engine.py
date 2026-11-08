"""Aptitude culturale : compare les besoins d'une culture aux conditions d'un lieu.

Méthode FAO (EcoCrop) : chaque facteur donne un score 0..1 par trapèze, et le
facteur le plus limitant décide du verdict global (loi du minimum, Liebig).
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


def assess(crop_id: str, site: dict[str, float | None]) -> dict[str, Any]:
    """Évalue une culture sur un site.

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
        value = site.get(factor)
        if value is None:
            unknown.append(factor)
            continue
        factors[factor] = {"value": float(value), "score": round(trapezoid(float(value), *crop[key]), 3)}

    if not factors:
        return {"crop": crop_id, "score": None, "verdict": "unknown", "limiting": None,
                "factors": {}, "unknown": unknown, "confidence": 0.0, "verified": crop["verified"]}

    limiting = min(factors, key=lambda f: factors[f]["score"])
    score = factors[limiting]["score"]
    return {
        "crop": crop_id,
        "score": score,
        "verdict": verdict_for(score),
        "limiting": limiting,
        "factors": factors,
        "unknown": unknown,
        "confidence": round(len(factors) / len(FACTORS), 2),
        "verified": crop["verified"],
    }


def rank(site: dict[str, float | None]) -> list[dict[str, Any]]:
    """Toutes les cultures classées de la plus adaptée à la moins adaptée."""
    results = [assess(cid, site) for cid in load_crops()]
    return sorted(results, key=lambda r: (r["score"] is None, -(r["score"] or 0)))
