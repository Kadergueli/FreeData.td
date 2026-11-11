"""Registre des licences des sources : ce qu'on a lu, quand, et ce que cela autorise."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

REGISTER_FILE = Path(__file__).with_name("licences_register.json")
COMMERCIAL_VALUES = ("yes", "no", "conditional", "unknown")

router = APIRouter(prefix="/api/v1/licences", tags=["licences"])


@lru_cache(maxsize=1)
def load_register() -> list[dict[str, Any]]:
    return json.loads(REGISTER_FILE.read_text(encoding="utf-8"))["sources"]


def commercial_safe(entry: dict[str, Any]) -> bool:
    """Utilisable dans une offre commerciale : autorisé ET vérifié sur la page officielle."""
    return entry["commercial_use"] == "yes" and bool(entry["verified_on"])


def public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {**entry, "commercial_safe": commercial_safe(entry)}


@router.get("")
def list_licences() -> dict[str, Any]:
    sources = [public_entry(e) for e in load_register()]
    return {
        "sources": sources,
        "summary": {
            "total": len(sources),
            "commercial_safe": sum(s["commercial_safe"] for s in sources),
            "share_alike": sum(bool(s["share_alike"]) for s in sources),
            "not_commercial": sum(s["commercial_use"] == "no" for s in sources),
            "unverified": sum(not s["verified_on"] for s in sources),
        },
    }
