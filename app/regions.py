"""One spelling for every region name, whatever the source wrote.

The sources do not agree: "Guéra" / "Guera", "Mayo Kebbi Est" / "Mayo-Kebbi Est", "Barh El Gazal" /
"Barh el Gazel", "Ndjaména" / "N'Djamena", "Abéché (Ouaddaï)" / "Abeche (Ouaddai)". Because the
region is part of the unique key of a row, those differences also hid duplicates and split one
series into several. Every row now goes through `canonical_region` when it is written, and
`supabase/maintenance/2026-10_09_unify_region_names.sql` applies the same rules to the rows
already stored.

Forms kept:  "national"  |  "Province"  |  "Place (Province)"  with the 23 provinces spelled
without accents, exactly like the INSEED and FEWS NET series.
"""
from __future__ import annotations

import re
import unicodedata

PROVINCES = (
    "Batha", "Barh el Gazel", "Borkou", "Chari-Baguirmi", "Ennedi Est", "Ennedi Ouest", "Guera",
    "Hadjer-Lamis", "Kanem", "Lac", "Logone Occidental", "Logone Oriental", "Mandoul",
    "Mayo-Kebbi Est", "Mayo-Kebbi Ouest", "Moyen-Chari", "N'Djamena", "Ouaddai", "Salamat",
    "Sila", "Tandjile", "Tibesti", "Wadi Fira",
)

# Spellings seen in the sources that the plain "letters only" key does not already catch.
_PROVINCE_ALIASES = {"barhelgazal": "Barh el Gazel", "bahrelgazal": "Barh el Gazel", "bahrelgazel": "Barh el Gazel"}

# A place that two sources write differently, or that one source writes without its province.
_PLACES = {
    "oumhadjer": ("Oum Hadjer", "Batha"),
    "amdjarass": ("Am-Djarass", "Ennedi Est"),
}


def _plain(text: str) -> str:
    """Without accents, single spaces."""
    ascii_text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.replace("’", "'").split())


def _key(text: str) -> str:
    """Letters only, lower case: 'Mayo Kebbi Est', 'Mayo-Kebbi Est' and 'mayo-kebbi est' all give 'mayokebbiest'."""
    return re.sub(r"[^a-z]", "", _plain(text).lower())


_PROVINCE_BY_KEY = {_key(p): p for p in PROVINCES} | _PROVINCE_ALIASES
_PROVINCE_BY_KEY["ndjamena"] = "N'Djamena"


def canonical_province(text: str) -> str | None:
    return _PROVINCE_BY_KEY.get(_key(text))


def _fix_ndjamena(place: str) -> str:
    return re.sub(r"(?i)\bn'?djamena\b", "N'Djamena", place)


def canonical_region(value: str | None) -> str:
    """The canonical spelling of a region label ('national' when empty). Unknown names are kept,
    only cleaned of accents and extra spaces."""
    text = _plain(str(value or ""))
    if not text or text.lower() in ("national", "all", "tous", "tout le tchad"):
        return "national"

    # "Place (Province)": the province is the LAST parenthesised group, the place is what precedes it.
    match = re.match(r"^(.*)\(([^()]*)\)\s*$", text)
    if match and match.group(1).strip():
        place, province_text = match.group(1).strip(), match.group(2).strip()
        province = canonical_province(province_text)
        if province is None:                      # "N'djamena (Atrone)": the bracket is part of the place
            return _fix_ndjamena(text)
        alias = _PLACES.get(_key(place))
        if alias:
            place = alias[0]
        if _key(place) == "ndjamena":
            return "N'Djamena (N'Djamena)"        # the capital is its own province, whatever a source says
        return f"{_fix_ndjamena(place)} ({province})"

    province = canonical_province(text)
    if province:
        return province
    alias = _PLACES.get(_key(text))
    if alias:
        return f"{alias[0]} ({alias[1]})"
    return _fix_ndjamena(text)
