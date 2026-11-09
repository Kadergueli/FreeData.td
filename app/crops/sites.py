"""Données d'un lieu : sols (SoilGrids) et climat (NASA POWER), lues dans deux fichiers du dépôt."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.crops.profile import build_profile

HERE = Path(__file__).parent
SOILS_FILE = HERE / "soils.json"
CLIMATE_FILE = HERE / "climate.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")).get("regions", {}) if path.exists() else {}


@lru_cache(maxsize=1)
def load_soils() -> dict[str, dict[str, Any]]:
    return _load(SOILS_FILE)


@lru_cache(maxsize=1)
def load_climate() -> dict[str, dict[str, Any]]:
    return _load(CLIMATE_FILE)


def _plain(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « abeche » trouve « Abéché (Ouaddaï) », « ndjamena » trouve « N'Djamena »."""
    folded = "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", folded)


def region_names() -> list[str]:
    return sorted(set(load_soils()) | set(load_climate()))


def find_region(query: str) -> str | None:
    """Nom exact de la région la plus proche de `query` (nom complet, ville ou province), ou None."""
    wanted = _plain(query.strip())
    if not wanted:
        return None
    names = region_names()
    for name in names:
        if _plain(name) == wanted:
            return name
    for name in names:
        if _plain(name).startswith(wanted):
            return name
    for name in names:
        if wanted in _plain(name):
            return name
    return None


def site_for(region: str) -> dict[str, Any]:
    """Facteurs du moteur pour une région exacte, plus ce qui manque. `site` ne contient que ce qui est connu."""
    site: dict[str, Any] = {}
    missing: list[str] = []
    climate, soil = load_climate().get(region), load_soils().get(region)
    if climate:
        site.update(build_profile(climate["rain_mm_day"], climate["temp_c"]))
    else:
        missing.append("climate")
    if soil and soil.get("ph") is not None:
        site["ph"] = soil["ph"]
    else:
        missing.append("soil")
    return {"region": region, "site": site, "soil": soil, "missing": missing}
