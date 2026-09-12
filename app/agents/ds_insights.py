"""
Module : DS Insights — Analyses Cross-Secteurs Avancées (FreeData.td)

Implémente :
  1. Score de fraîcheur des données par secteur (jours depuis dernière observation)
  2. Matrice de corrélation temporelle croisée entre secteurs
  3. Détection d'anomalies saisonnières (conscience de la soudure juin-septembre)
  4. Couverture spatiale par province/région du Tchad
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Mois de soudure au Tchad : juin (6) à septembre (9)
# Pendant cette période, une variance plus élevée des prix agricoles est normale
_SOUDURE_MONTHS = {6, 7, 8, 9}

# Secteurs reconnus par la plateforme
_KNOWN_SECTORS = [
    "agriculture", "markets", "environment", "economy",
    "health", "energy", "education", "transport",
]

# Paires de secteurs pour l'analyse de corrélation croisée
_SECTOR_PAIRS = [
    ("environment", "markets"),      # Précipitations → Prix des céréales (décalage ~2 mois)
    ("environment", "agriculture"),  # Climat → Rendements agricoles
    ("markets", "economy"),          # Prix → Inflation macroéconomique
    ("health", "economy"),           # Couverture sanitaire → PIB/habitant
]


def _parse_date(raw: Any) -> date | None:
    """Convertit une valeur de date brute en objet date Python, sans lever d'exception."""
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(str(raw)).date()
    except (ValueError, TypeError):
        pass
    try:
        parts = str(raw).split("-")
        if len(parts) >= 2:
            return date(int(parts[0]), int(parts[1][:2]), 1)
    except (ValueError, IndexError):
        pass
    return None


def _zscore_anomaly(values: list[float], threshold: float = 3.0) -> list[bool]:
    """Modified Z-Score (médiane + MAD) pour une détection d'anomalies robuste.

    Utilise la médiane (résistante aux valeurs extrêmes) plutôt que la moyenne
    arithmétique, adapté aux séries temporelles macro-économiques asymétriques.
    """
    if len(values) < 4:
        return [False] * len(values)
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return [False] * len(values)
    return [0.6745 * abs(v - med) / mad > threshold for v in values]


def _pearson_r(x: list[float], y: list[float]) -> float:
    """Calcule le coefficient de corrélation de Pearson entre deux séries."""
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


def compute_freshness_scores(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Score de fraîcheur des données par secteur.

    Pour chaque secteur :
      - last_date : date de la dernière observation
      - days_ago : jours depuis la dernière observation
      - freshness_score : 0.0 (obsolète) → 1.0 (très récent), décroissance exponentielle (demi-vie 30j)
      - status : "fresh" (≤7j) | "recent" (≤30j) | "stale" (≤90j) | "outdated" (>90j) | "no_data"
      - obs_count : nombre total d'observations pour ce secteur
    """
    latest_by_sector: dict[str, date] = {}
    counts_by_sector: dict[str, int] = defaultdict(int)
    today = datetime.now(UTC).date()

    for obs in observations:
        sector = obs.get("sector", "")
        if not sector:
            continue
        counts_by_sector[sector] += 1
        d = _parse_date(obs.get("reference_date"))
        if d and (sector not in latest_by_sector or d > latest_by_sector[sector]):
            latest_by_sector[sector] = d

    result: dict[str, dict[str, Any]] = {}
    for sector in _KNOWN_SECTORS:
        last = latest_by_sector.get(sector)
        obs_count = counts_by_sector.get(sector, 0)
        if last is None:
            result[sector] = {
                "last_date": None,
                "days_ago": None,
                "freshness_score": 0.0,
                "status": "no_data",
                "obs_count": obs_count,
            }
            continue
        days_ago = (today - last).days
        score = math.exp(-days_ago / 30.0)
        if days_ago <= 7:
            status = "fresh"
        elif days_ago <= 30:
            status = "recent"
        elif days_ago <= 90:
            status = "stale"
        else:
            status = "outdated"
        result[sector] = {
            "last_date": last.isoformat(),
            "days_ago": days_ago,
            "freshness_score": round(score, 4),
            "status": status,
            "obs_count": obs_count,
        }
    return result


def compute_cross_sector_correlations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Corrélation temporelle croisée entre paires de secteurs stratégiques.

    Méthode : alignement sur l'axe mensuel (AAAA-MM), coefficient de Pearson
    sur les moyennes mensuelles normalisées, testé avec un décalage (lag) de
    0, 1 et 2 mois pour détecter des effets retardés.

    Chaque entrée retournée contient :
      - sector_a, sector_b : les deux secteurs comparés
      - lag_months : décalage qui maximise la corrélation absolue
      - correlation : coefficient r ∈ [-1, 1]
      - strength : "strong" (|r|≥0.7) | "moderate" (≥0.4) | "weak" (≥0.2) | "none"
      - interpretation : description institutionnelle en français
    """
    monthly: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for obs in observations:
        sector = obs.get("sector", "")
        val = obs.get("value")
        if not sector or not isinstance(val, (int, float)):
            continue
        d = _parse_date(obs.get("reference_date"))
        if not d:
            continue
        key = f"{d.year}-{d.month:02d}"
        monthly[sector][key].append(float(val))

    means: dict[str, dict[str, float]] = {}
    for sector, months in monthly.items():
        means[sector] = {k: statistics.mean(v) for k, v in months.items()}

    results = []
    for sector_a, sector_b in _SECTOR_PAIRS:
        ma = means.get(sector_a, {})
        mb = means.get(sector_b, {})
        if len(ma) < 4 or len(mb) < 4:
            results.append({
                "sector_a": sector_a,
                "sector_b": sector_b,
                "lag_months": 0,
                "correlation": None,
                "strength": "insufficient_data",
                "interpretation": (
                    "Données insuffisantes pour établir une corrélation fiable "
                    "(minimum 4 points mensuels requis par secteur)."
                ),
            })
            continue

        best_r = 0.0
        best_lag = 0
        all_months_a = sorted(ma.keys())

        for lag in range(0, 3):
            paired_a: list[float] = []
            paired_b: list[float] = []
            for ym in all_months_a:
                y, m = int(ym.split("-")[0]), int(ym.split("-")[1])
                future_m = m + lag
                future_y = y + (future_m - 1) // 12
                future_m = ((future_m - 1) % 12) + 1
                future_key = f"{future_y}-{future_m:02d}"
                if future_key in mb:
                    paired_a.append(ma[ym])
                    paired_b.append(mb[future_key])

            if len(paired_a) < 4:
                continue
            try:
                r = _pearson_r(paired_a, paired_b)
            except Exception:
                continue
            if abs(r) > abs(best_r):
                best_r = r
                best_lag = lag

        strength = (
            "strong" if abs(best_r) >= 0.7
            else "moderate" if abs(best_r) >= 0.4
            else "weak" if abs(best_r) >= 0.2
            else "none"
        )
        direction = "augmente" if best_r >= 0 else "diminue"
        lag_note = f" avec un décalage de {best_lag} mois" if best_lag > 0 else ""
        interpretation = (
            f"Corrélation {'positive' if best_r >= 0 else 'négative'} "
            f"({strength}){lag_note} entre {sector_a.capitalize()} et "
            f"{sector_b.capitalize()} (r = {best_r:.2f}) : quand {sector_a} évolue, "
            f"{sector_b} tend à {direction}{lag_note}."
        )

        results.append({
            "sector_a": sector_a,
            "sector_b": sector_b,
            "lag_months": best_lag,
            "correlation": round(best_r, 4),
            "strength": strength,
            "interpretation": interpretation,
        })

    return results


def compute_spatial_coverage(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyse de couverture géographique des observations.

    Retourne :
      - regions_covered : liste des régions avec au moins 1 observation
      - total_regions : nombre de régions distinctes
      - coverage_rate : ratio par rapport aux 23 provinces du Tchad
      - sectors_per_region : secteurs disponibles par région
      - sparsest_regions : régions avec moins de 2 secteurs de données
    """
    TOTAL_CHAD_PROVINCES = 23
    region_sectors: dict[str, set[str]] = defaultdict(set)

    for obs in observations:
        raw_reg = (obs.get("region") or "").strip()
        sector = obs.get("sector", "")
        if not raw_reg or raw_reg.lower() in ("", "national", "tcd", "tchad"):
            continue
        # Extract official province name if formatted as "City (Province)"
        if "(" in raw_reg and ")" in raw_reg:
            prov = raw_reg.split("(")[1].split(")")[0].strip()
        else:
            prov = raw_reg
        region_sectors[prov].add(sector)

    regions = list(region_sectors.keys())
    coverage_rate = min(len(regions) / TOTAL_CHAD_PROVINCES, 1.0)
    sparsest = [r for r, s in region_sectors.items() if len(s) < 2]

    return {
        "regions_covered": sorted(regions),
        "total_regions": len(regions),
        "coverage_rate": round(coverage_rate, 4),
        "sectors_per_region": {r: sorted(list(s)) for r, s in sorted(region_sectors.items())},
        "sparsest_regions": sorted(sparsest),
        "total_chad_provinces": TOTAL_CHAD_PROVINCES,
    }


def compute_seasonal_anomalies(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Détection d'anomalies statistiques avec conscience de la saisonnalité tchadienne.

    Pendant la période de soudure (juin-septembre), le seuil d'anomalie est
    assoupli pour les secteurs agriculture et markets (variance naturellement élevée).
    Pour les autres secteurs et périodes, le Modified Z-Score standard (seuil 3.0) est utilisé.

    Retourne la liste des observations anormales détectées avec leur contexte.
    """
    groups: dict[tuple[str, str, int], list[tuple[float, dict[str, Any]]]] = defaultdict(list)
    for obs in observations:
        sector = obs.get("sector", "")
        indicator = obs.get("indicator", "")
        val = obs.get("value")
        if not isinstance(val, (int, float)):
            continue
        d = _parse_date(obs.get("reference_date"))
        month = d.month if d else 0
        groups[(sector, indicator, month)].append((float(val), obs))

    anomalies = []
    for (sector, indicator, month), pairs in groups.items():
        if len(pairs) < 4:
            continue
        values = [p[0] for p in pairs]
        # Seuil assoupli (relevé) pendant la soudure pour agriculture et marchés :
        # la variance des prix y est naturellement plus élevée à cette période, donc
        # il faut un écart PLUS extrême pour déclencher une alerte (moins sensible),
        # sans quoi la variation saisonnière normale serait signalée comme anomalie.
        threshold = 3.5 if (sector in ("agriculture", "markets") and month in _SOUDURE_MONTHS) else 3.0
        flags = _zscore_anomaly(values, threshold=threshold)

        for is_anomaly, (val, obs) in zip(flags, pairs):
            if is_anomaly:
                anomalies.append({
                    "sector": sector,
                    "indicator": indicator,
                    "value": val,
                    "unit": obs.get("unit", ""),
                    "region": obs.get("region", ""),
                    "reference_date": obs.get("reference_date"),
                    "source": obs.get("source", ""),
                    "is_soudure_period": month in _SOUDURE_MONTHS,
                    "threshold_used": threshold,
                })

    anomalies.sort(key=lambda x: (x["sector"], str(x.get("reference_date") or "")))
    return anomalies
