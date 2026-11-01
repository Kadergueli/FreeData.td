"""Lens « marchés » : prix de détail des produits de base (PAM / WFP) par marché.

Les marchés sont découverts dans la base (régions de la forme « Lieu (Province) »), si bien qu'un
nouveau marché collecté devient utilisable sans modifier ce fichier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from app.assistant.text import (
    find_alias, fmt_month, fmt_number, fmt_unit, normalize, parse_date,
)
from app.regions import canonical_province

# Produit tel qu'écrit en base (avant « retail price (WFP) ») -> façons de le dire en français,
# déjà normalisées (minuscules, sans accents). Le plus long alias l'emporte : « riz local » > « riz ».
PRODUCT_ALIASES: dict[str, list[str]] = {
    "Millet": ["mil", "millet"],
    "Sorghum": ["sorgho", "sorgho blanc"],
    "Sorghum (red)": ["sorgho rouge"],
    "Sorghum (berbere)": ["berbere", "berbere sorgho"],
    "Maize (white)": ["mais", "mais blanc"],
    "Wheat": ["ble"],
    "Wheat flour": ["farine", "farine de ble"],
    "Rice (imported)": ["riz", "riz importe"],
    "Rice (local)": ["riz local"],
    "Pasta": ["pates", "pate", "macaroni", "spaghetti"],
    "Sugar": ["sucre"],
    "Salt": ["sel"],
    "Oil (groundnut)": ["huile", "huile d'arachide"],
    "Groundnuts (shelled)": ["arachide", "arachides"],
    "Peanut": ["cacahuete", "cacahuetes"],
    "Sesame": ["sesame"],
    "Beans (niebe)": ["niebe", "haricot", "haricots", "haricot niebe"],
    "Beans (niebe, red)": ["niebe rouge", "haricot rouge"],
    "Cassava (cossette)": ["manioc", "cossette"],
    "Sweet potatoes": ["patate douce", "patates douces"],
    "Onions (red)": ["oignon", "oignons"],
    "Garlic": ["ail"],
    "Okra (dry)": ["gombo", "gombo sec"],
    "Tomatoes (dried)": ["tomate", "tomates", "tomate sechee"],
    "Mangoes": ["mangue", "mangues"],
    "Dates": ["datte", "dattes"],
    "Fish (dry)": ["poisson sec", "poisson"],
    "Livestock (cattle)": ["boeuf", "bovin", "bovins", "vache", "taureau"],
    "Livestock (goat, medium-sized castrated male)": ["chevre", "caprin", "caprins", "bouc"],
    "Livestock (sheep, medium-sized castrated male)": ["mouton", "ovin", "ovins", "belier"],
}

# Noms d'affichage français (la base écrit sans accents).
DISPLAY_PRODUCT = {
    "Millet": "le mil", "Sorghum": "le sorgho", "Sorghum (red)": "le sorgho rouge",
    "Sorghum (berbere)": "le sorgho berbéré", "Maize (white)": "le maïs blanc", "Wheat": "le blé",
    "Wheat flour": "la farine de blé", "Rice (imported)": "le riz importé", "Rice (local)": "le riz local",
    "Pasta": "les pâtes", "Sugar": "le sucre", "Salt": "le sel", "Oil (groundnut)": "l'huile d'arachide",
    "Groundnuts (shelled)": "l'arachide décortiquée", "Peanut": "la cacahuète", "Sesame": "le sésame",
    "Beans (niebe)": "le niébé", "Beans (niebe, red)": "le niébé rouge", "Cassava (cossette)": "le manioc (cossettes)",
    "Sweet potatoes": "la patate douce", "Onions (red)": "l'oignon rouge", "Garlic": "l'ail",
    "Okra (dry)": "le gombo sec", "Tomatoes (dried)": "la tomate séchée", "Mangoes": "la mangue",
    "Dates": "les dattes", "Fish (dry)": "le poisson sec", "Livestock (cattle)": "le bœuf",
    "Livestock (goat, medium-sized castrated male)": "la chèvre (bouc castré moyen)",
    "Livestock (sheep, medium-sized castrated male)": "le mouton (bélier castré moyen)",
}

_ACCENTS = {"Abeche": "Abéché", "Adre": "Adré", "Dembe": "Dembé", "Ouaddai": "Ouaddaï", "Guera": "Guéra",
            "Tandjile": "Tandjilé", "Biltine": "Biltine", "Laï": "Laï", "Marche": "Marché", "Mil": "Mil"}

# Marchés connus au démarrage ; la base en ajoute d'autres (voir MarketDirectory.from_regions).
SEED_REGIONS = (
    "Abeche (Ouaddai)", "Adre (Ouaddai)", "Dembe (N'Djamena)",
    "N'Djamena (Atrone) (N'Djamena)", "N'Djamena (Marche A Mil) (N'Djamena)", "N'Djamena",
)

SOURCE_LABEL = {"WFP": "PAM (WFP)"}


def pretty(name: str) -> str:
    """'Abeche (Ouaddai)' -> 'Abéché (Ouaddaï)'; 'N'Djamena (Marche A Mil) (N'Djamena)' -> 'Marché à Mil (N'Djamena)'."""
    out = re.sub(r"^N'Djamena \((.+)\) \(N'Djamena\)$", r"\1 (N'Djamena)", name)
    out = re.sub(r"\b(Marche A Mil)\b", "Marché à Mil", out)
    for plain, accented in _ACCENTS.items():
        out = re.sub(rf"\b{plain}\b", accented, out)
    return out


def spoken(name: str) -> str:
    """Nom de lieu court pour une phrase : « Abéché » (la province n'apporte rien), mais « Dembé (N'Djamena) »."""
    full = pretty(name)
    m = re.match(r"^(.+?) \(([^()]+)\)$", full)
    if m and m.group(2) != "N'Djamena" and not m.group(1).endswith(")"):
        return m.group(1)
    return full


def de_product(product: str) -> str:
    """'le riz' -> 'du riz', 'la farine' -> 'de la farine', "l'huile" -> "de l'huile", 'les pâtes' -> 'des pâtes'."""
    label = DISPLAY_PRODUCT.get(product, product)
    if label.startswith("le "):
        return "du " + label[3:]
    if label.startswith("la "):
        return "de " + label
    if label.startswith("les "):
        return "des " + label[4:]
    if label.startswith("l'"):
        return "de " + label
    return "de " + label


@dataclass(frozen=True)
class Market:
    name: str                 # nom EXACT de la région en base
    province: str | None      # province canonique, pour masquer la ligne générale d'une ville citée
    aliases: tuple[str, ...]  # façons de l'écrire, normalisées
    generic: bool = False     # ligne « ville / province entière », sans marché précis


def _market_from_region(region: str) -> Market | None:
    province = canonical_province(region)
    if province:                                           # « N'Djamena », « Ouaddai » : ligne générale
        aliases = {normalize(province), normalize(province).replace("'", "").replace(" ", "")}
        aliases.add(normalize(province).replace("'", " "))
        return Market(region, province, tuple(sorted(a for a in aliases if a)), True)
    m = re.match(r"^(?P<place>.+?) \((?P<prov>[^()]+)\)$", region)
    if not m:
        return None
    prov = canonical_province(m["prov"])
    if not prov:
        return None
    place = m["place"]
    inner = re.search(r"\(([^()]+)\)$", place)
    label = inner[1] if inner else place                  # « Atrone » dans « N'Djamena (Atrone) »
    aliases = {normalize(label)}
    if normalize(label).startswith("marche a "):
        aliases.add("marche au " + normalize(label)[len("marche a "):])
    return Market(region, prov, tuple(sorted(a for a in aliases if a)), False)


class MarketDirectory:
    def __init__(self, markets: Iterable[Market]) -> None:
        self.markets = list(markets)

    @classmethod
    def from_regions(cls, regions: Iterable[str] = ()) -> "MarketDirectory":
        seen: dict[str, Market] = {}
        for r in list(SEED_REGIONS) + [str(x) for x in regions]:
            if r not in seen:
                m = _market_from_region(r)
                if m:
                    seen[r] = m
        return cls(seen.values())

    def find(self, norm_text: str) -> list[tuple[Market, tuple[int, int]]]:
        """Marchés cités, dans l'ordre d'apparition, avec leur position dans le texte normalisé.
        Si un marché précis d'une province est cité, la ligne générale de cette province est ignorée."""
        hits: list[tuple[Market, tuple[int, int]]] = []
        for m in self.markets:
            spans = [s for a in m.aliases if (s := find_alias(norm_text, a))]
            if spans:
                hits.append((m, min(spans)))
        specific = {m.province for m, _ in hits if not m.generic}
        hits = [(m, s) for m, s in hits if not (m.generic and m.province in specific)]
        # un alias contenu dans un autre (« mil » dans « marche a mil ») ne compte qu'une fois
        return sorted(hits, key=lambda h: h[1][0])


# ── produits ────────────────────────────────────────────────────────────
def find_product(norm_text: str) -> str | None:
    """Le produit cité (nom en base) ; l'alias le plus long gagne, puis le plus tôt dans la phrase."""
    best: tuple[int, int, str] | None = None
    for product, aliases in PRODUCT_ALIASES.items():
        for alias in aliases:
            span = find_alias(norm_text, alias)
            if span:
                key = (-len(alias), span[0], product)
                if best is None or key < best:
                    best = key
    return best[2] if best else None


def find_products(norm_text: str, limit: int = 4) -> list[str]:
    """Tous les produits cités, dans l'ordre de la phrase ; un alias contenu dans un alias plus long est ignoré
    (« riz » dans « riz local »)."""
    hits: list[tuple[int, int, str]] = []        # (début, fin, produit)
    for product, aliases in PRODUCT_ALIASES.items():
        for alias in aliases:
            span = find_alias(norm_text, alias)
            if span:
                hits.append((span[0], span[1], product))
    hits.sort(key=lambda h: -(h[1] - h[0]))       # les plus longs d'abord
    kept: list[tuple[int, int, str]] = []
    for start, end, product in hits:
        if any(start < k_end and k_start < end for k_start, k_end, _ in kept) or any(product == k[2] for k in kept):
            continue
        kept.append((start, end, product))
    return [h[2] for h in sorted(kept)[:limit]]


# ── données ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PriceResult:
    market: str
    product: str
    value: float
    unit: str
    date: str
    source: str


@dataclass(frozen=True)
class Comparison:
    a: PriceResult
    b: PriceResult
    same_period: bool
    cheaper: str | None
    gap_pct: float


def _indicator(product: str) -> str:
    return f"{product} retail price (WFP)"


def price_history(repo, product: str, market: str) -> list[PriceResult]:
    """Prix connus (un par date, les plus récents d'abord)."""
    wanted = _indicator(product)
    # Filtre EXACT sur l'indicateur : une recherche par mot (« Rice ») trouverait aussi « ... retail p-rice » de tous les produits.
    rows = repo.list_observations(sector="markets", region=market, limit=120, indicator=wanted)
    out: dict[str, PriceResult] = {}
    for r in rows:
        if r.get("indicator") != wanted or r.get("region") != market:
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError, KeyError):
            continue
        d = str(r.get("reference_date"))[:10]
        out.setdefault(d, PriceResult(market, product, value, r.get("unit") or "", d, r.get("source") or ""))
    return sorted(out.values(), key=lambda p: p.date, reverse=True)


def ranking(repo, product: str, max_gap_days: int = 45) -> list[PriceResult]:
    """Dernier prix de chaque marché, du moins cher au plus cher, en ne gardant que les marchés dont le relevé
    est du même ordre de date que le plus récent (sinon on compare des mois différents)."""
    wanted = _indicator(product)
    rows = repo.list_observations(sector="markets", region=None, limit=600, indicator=wanted)
    latest: dict[str, PriceResult] = {}
    for r in rows:                                # plus récent d'abord
        region = r.get("region")
        if r.get("indicator") != wanted or not region or region in latest:
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError, KeyError):
            continue
        latest[region] = PriceResult(region, product, value, r.get("unit") or "", str(r.get("reference_date"))[:10],
                                     r.get("source") or "")
    if not latest:
        return []
    newest = max(parse_date(p.date) for p in latest.values())
    fresh = [p for p in latest.values() if (newest - parse_date(p.date)).days <= max_gap_days]
    return sorted(fresh, key=lambda p: p.value)


def latest_price(repo, product: str, market: str) -> PriceResult | None:
    history = price_history(repo, product, market)
    return history[0] if history else None


def compare_markets(repo, product: str, market_a: str, market_b: str) -> Comparison | None:
    a, b = latest_price(repo, product, market_a), latest_price(repo, product, market_b)
    if a is None or b is None:
        return None
    same = a.date == b.date
    if a.value == b.value:
        return Comparison(a, b, same, None, 0.0)
    low, high = (a, b) if a.value < b.value else (b, a)
    return Comparison(a, b, same, low.market, round((high.value - low.value) / low.value * 100, 1))


def price_change(history: list[PriceResult], months: int = 3) -> tuple[PriceResult, PriceResult, float] | None:
    """(ancien prix, dernier prix, variation en %) en remontant d'environ `months` mois.
    Prend la date disponible la plus proche de la cible, au moins 45 jours avant le dernier prix."""
    if len(history) < 2:
        return None
    latest = history[0]
    latest_d = parse_date(latest.date)
    target = latest_d - timedelta(days=30 * months)
    candidates = [p for p in history[1:] if (latest_d - parse_date(p.date)).days >= 45]
    if not candidates:
        return None
    old = min(candidates, key=lambda p: abs((parse_date(p.date) - target).days))
    if old.value == 0:
        return None
    return old, latest, round((latest.value - old.value) / old.value * 100, 1)


# ── phrases ─────────────────────────────────────────────────────────────
def money(value: float, unit: str) -> str:
    """« 204 XAF le kilo », « 1 500 XAF le litre », « 150 000 XAF par tête »."""
    number = fmt_number(value, 0 if value >= 100 else 1)
    currency, _, per = (unit or "").partition("/")
    spoken = {"KG": "le kilo", "L": "le litre", "HEAD": "par tête", "TETE": "par tête"}.get(per.upper())
    if currency and spoken:
        return f"{number} {currency} {spoken}"
    return f"{number} {fmt_unit(unit)}".strip()


def _freshness(price_date: str, today: date) -> str:
    d = parse_date(price_date)
    if d and (today - d).days > 60:
        return (f" Attention, ce relevé a plus de {(today - d).days // 30} mois : le PAM publie ses prix avec du retard, "
                "le prix d'aujourd'hui peut être différent.")
    return ""


def src_name(source: str) -> str:
    return SOURCE_LABEL.get(source, source)


def describe_price(p: PriceResult, today: date) -> str:
    product = DISPLAY_PRODUCT.get(p.product, p.product)
    return (f"À {spoken(p.market)}, {product} se vend {money(p.value, p.unit)} "
            f"(dernier relevé : {fmt_month(p.date)}, source {src_name(p.source)}).{_freshness(p.date, today)}")
