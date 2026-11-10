"""Ajoute des cultures à requirements.json à partir de la base FAO EcoCrop (EcoCrop_DB.csv, OpenCLIM/ecocrop).

Usage : python -m app.crops.ecocrop_import chemin/EcoCrop_DB.csv
Aucune valeur n'est inventée : une culture dont le cycle est absent (0) de la base n'est pas ajoutée.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REQUIREMENTS = Path(__file__).with_name("requirements.json")
SOURCE = "FAO EcoCrop, via OpenCLIM/ecocrop EcoCrop_DB.csv"

# id -> (code EcoPort, nom français, nom anglais)
WANTED = {
    "onion": (364, "Oignon", "Onion"),
    "tomato": (1379, "Tomate", "Tomato"),
    "okra": (289, "Gombo", "Okra"),
    "sweet_potato": (1265, "Patate douce", "Sweet potato"),
    "wheat": (2114, "Blé", "Wheat"),
    "bambara": (10830, "Voandzou (pois bambara)", "Bambara groundnut"),
    "pepper": (618, "Piment", "Pepper"),
    "bean": (1668, "Haricot commun", "Common bean"),
    "soybean": (1150, "Soja", "Soybean"),
    "potato": (1971, "Pomme de terre", "Potato"),
    "sugarcane": (1884, "Canne à sucre", "Sugarcane"),
}


def _nums(row: dict[str, str], keys: tuple[str, ...]) -> list[float] | None:
    try:
        vals = [float(row[k]) for k in keys]
    except (KeyError, ValueError):
        return None
    vals = [int(v) if v == int(v) else v for v in vals]
    return vals if vals == sorted(vals) else None


def _list(text: str) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def build(csv_path: Path) -> tuple[dict[str, dict], list[str]]:
    with open(csv_path, encoding="latin-1", newline="") as fh:
        by_code = {int(r["EcoPortCode"]): r for r in csv.DictReader(fh) if r["EcoPortCode"].isdigit()}
    out: dict[str, dict] = {}
    skipped: list[str] = []
    for crop_id, (code, fr, en) in WANTED.items():
        row = by_code.get(code)
        if row is None:
            skipped.append(f"{crop_id}: code {code} absent")
            continue
        rain = _nums(row, ("RMIN", "ROPMN", "ROPMX", "RMAX"))
        temp = _nums(row, ("TMIN", "TOPMN", "TOPMX", "TMAX"))
        ph = _nums(row, ("PHMIN", "PHOPMN", "PHOPMX", "PHMAX"))
        cycle = _nums(row, ("GMIN", "GMAX"))
        if not (rain and temp and ph and cycle) or cycle[0] <= 0:
            skipped.append(f"{crop_id}: données incomplètes")
            continue
        out[crop_id] = {"fr": fr, "en": en, "scientific_name": row["ScientificName"], "ecoport_code": code,
                        "rain_mm": rain, "temp_mean_c": temp, "ph": ph, "cycle_days": cycle,
                        "texture_optimal": _list(row.get("TEXT", "")), "texture_tolerated": _list(row.get("TEXTR", "")),
                        "source": SOURCE, "verified": True}
    return out, skipped


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    new, skipped = build(Path(argv[1]))
    doc = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    for crop_id, entry in new.items():
        doc["crops"].setdefault(crop_id, entry)  # n'écrase jamais une culture existante
    REQUIREMENTS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(new)} cultures lues, {len(doc['crops'])} au total ; ignorées : {skipped or 'aucune'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
