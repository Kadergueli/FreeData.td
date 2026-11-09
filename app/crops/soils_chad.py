"""Sols du Tchad pour FreeData.td : pH, argile, sable, carbone organique pour les 23 regions.

SoilGrids (ISRIC, CC BY 4.0) : l'API REST renvoie des valeurs vides pour le Tchad, donc on lit
directement les cartes (COG) a distance, uniquement aux 23 points : quelques Ko telecharges, pas les cartes entieres.

Installation (une fois) :   .venv\Scripts\pip install rasterio pyproj
  -> si rasterio ne s'installe pas (Python trop recent), lance ce fichier dans Google Colab (colab.research.google.com),
     puis telecharge soils.json avec le menu Fichiers.
Usage :   .venv\Scripts\python app\crops\soils_chad.py   (Duree : 2 a 10 minutes. Cree app/crops/soils.json et affiche un tableau.)
"""
import importlib
import json
from pathlib import Path
import sys
from typing import Any

try:
    rasterio: Any = importlib.import_module("rasterio")
    Transformer: Any = importlib.import_module("pyproj").Transformer
except ModuleNotFoundError:
    rasterio = None
    Transformer = None

BASE = "https://files.isric.org/soilgrids/latest/data"
# projection des cartes SoilGrids (Interrupted Goode Homolosine)
IGH = "+proj=igh +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}  # epaisseur en cm, pour la moyenne ponderee 0-30 cm
# propriete -> diviseur (SoilGrids stocke des entiers : pH*10, g/kg, dg/kg)
PROPS = {"phh2o": 10, "clay": 10, "sand": 10, "soc": 10}

REGIONS = {
    "N'Djamena (N'Djamena)": (12.11, 15.05), "Moundou (Logone Occidental)": (8.56, 16.08),
    "Doba (Logone Oriental)": (8.65, 16.85), "Sarh (Moyen-Chari)": (9.15, 18.39),
    "Koumra (Mandoul)": (8.93, 17.55), "Laï (Tandjilé)": (9.40, 16.30),
    "Bongor (Mayo-Kebbi Est)": (10.28, 15.37), "Pala (Mayo-Kebbi Ouest)": (9.36, 14.90),
    "Abéché (Ouaddaï)": (13.82, 20.83), "Biltine (Wadi Fira)": (14.53, 20.92),
    "Goz Beïda (Sila)": (12.22, 21.41), "Am Timan (Salamat)": (11.04, 20.28),
    "Mongo (Guéra)": (12.18, 18.69), "Ati (Batha)": (13.21, 18.34),
    "Mao (Kanem)": (14.12, 15.31), "Moussoro (Barh El Gazel)": (13.64, 16.49),
    "Bol (Lac)": (13.46, 14.71), "Massakory (Hadjer-Lamis)": (13.00, 15.73),
    "Massenya (Chari-Baguirmi)": (11.40, 16.17), "Faya-Largeau (Borkou)": (17.93, 19.11),
    "Am-Djarass (Ennedi Est)": (16.07, 22.84), "Fada (Ennedi Ouest)": (17.18, 21.58),
    "Bardaï (Tibesti)": (21.35, 17.00),
}


def main() -> int:
    if rasterio is None or Transformer is None:
        print(
            "Erreur : rasterio et pyproj sont requis.\n"
            "Installez-les avec : .venv\\Scripts\\pip install rasterio pyproj",
            file=sys.stderr,
        )
        return 1
    to_igh = Transformer.from_crs("EPSG:4326", IGH, always_xy=True)
    points = {name: to_igh.transform(lon, lat) for name, (lat, lon) in REGIONS.items()}
    values = {name: {} for name in REGIONS}  # name -> prop -> [(epaisseur, valeur)]
    for prop, div in PROPS.items():
        for depth, thick in DEPTHS.items():
            url = f"/vsicurl/{BASE}/{prop}/{prop}_{depth}_mean.vrt"
            print(f"Lecture {prop} {depth} ...", flush=True)
            try:
                with rasterio.open(url) as src:
                    for (name, xy), val in zip(points.items(), src.sample(list(points.values()))):
                        raw = float(val[0])
                        if (src.nodata is not None and raw == src.nodata) or raw < 0:
                            continue
                        values[name].setdefault(prop, []).append((thick, raw / div))
            except Exception as exc:  # une couche qui echoue ne bloque pas les autres
                print(f"  ECHEC {prop} {depth}: {exc}")
    out, missing = {}, []
    for name, props in values.items():
        row = {}
        for prop, pairs in props.items():
            total = sum(t for t, _ in pairs)
            row[prop] = round(sum(t * v for t, v in pairs) / total, 2)  # moyenne ponderee 0-30 cm
        if len(row) < len(PROPS):
            missing.append(name)
        out[name] = {"ph": row.get("phh2o"), "clay_pct": row.get("clay"), "sand_pct": row.get("sand"),
                     "organic_carbon_g_kg": row.get("soc")}
    doc = {"_note": "SoilGrids 2.0 (ISRIC, CC BY 4.0), moyenne ponderee 0-30 cm au point central de chaque region. "
                    "pH en eau ; argile et sable en % (g/100g) ; carbone organique en g/kg.",
           "source": "SoilGrids 2.0, https://www.isric.org/explore/soilgrids", "regions": out}
    out_path = Path(__file__).resolve().parent / "soils.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print(f"\n{'Region':34} {'pH':>5} {'argile%':>8} {'sable%':>7} {'C org g/kg':>11}")
    for name, r in out.items():
        print(f"{name:34} {r['ph']!s:>5} {r['clay_pct']!s:>8} {r['sand_pct']!s:>7} {r['organic_carbon_g_kg']!s:>11}")
    print(f"\n{out_path} ecrit. Regions incompletes : {len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())