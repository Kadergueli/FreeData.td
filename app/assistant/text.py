"""Shared text helpers: normalisation of questions and French formatting of figures and dates."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")


def normalize(text: str) -> str:
    """Lower case, no accents, curly apostrophes straightened, punctuation -> space, one space."""
    s = unicodedata.normalize("NFD", str(text or "").lower().replace("’", "'").replace("`", "'"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", s).split())


def find_alias(norm: str, alias: str) -> tuple[int, int] | None:
    """Span of `alias` as a WHOLE word (or words) inside the normalised text, else None.
    'mil' is found in 'prix du mil' but not in 'famille'."""
    m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm)
    return (m.start(), m.end()) if m else None


def parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def fmt_month(value) -> str:
    d = parse_date(value)
    return f"{MONTHS_FR[d.month - 1]} {d.year}" if d else str(value)


def fmt_day(value) -> str:
    d = parse_date(value)
    if not d:
        return str(value)
    return f"{'1er' if d.day == 1 else d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def fmt_number(value: float, decimals: int = 1) -> str:
    """French style: space for thousands, comma for decimals, no useless trailing zeros."""
    text = f"{float(value):,.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def fmt_unit(unit: str) -> str:
    """'XAF/KG' -> 'XAF/kg', 'XAF/L' -> 'XAF/L', '°C' unchanged."""
    return re.sub(r"/KG$", "/kg", unit or "")


def days_between(later: date, earlier: date) -> int:
    return (later - earlier).days
