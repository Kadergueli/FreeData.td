"""Climat du Tchad pour FreeData.td : pluie et temperature mensuelles moyennes des 23 regions (NASA POWER).

NASA POWER (domaine public NASA, sans cle) : climatologie mensuelle moyenne, pas une annee particuliere.
Aucune installation : bibliotheque standard seulement.
Usage :   .venv\\Scripts\\python app\\crops\\climate_chad.py       Duree : 1 a 3 minutes.  Cree climate.json a cote du script.
"""
import json
import os
import time
import urllib.error
import urllib.request

URL = ("https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=PRECTOTCORR,T2M"
       "&community=AG&longitude={lon}&latitude={lat}&format=JSON")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
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


def fetch(lat, lon):
    url = URL.format(lat=lat, lon=lon)
    if not url.startswith("https://power.larc.nasa.gov/"):
        raise ValueError(f"URL non autorisee: {url}")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FreeData.td/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:  # nosec B310
                return json.load(resp)["properties"]["parameter"]
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            print(f"   essai {attempt + 1} echoue : {exc}")
            time.sleep(3 * (attempt + 1))
    return None


def months(series):
    return {m: round(float(series[m]), 3) for m in MONTHS}


def main():
    out = {}
    for name, (lat, lon) in REGIONS.items():
        print(f"{name} ...", flush=True)
        data = fetch(lat, lon)
        if not data:
            print("   ABANDON")
            continue
        out[name] = {"rain_mm_day": months(data["PRECTOTCORR"]), "temp_c": months(data["T2M"])}
        time.sleep(1)
    doc = {"_note": "NASA POWER, climatologie mensuelle moyenne (PRECTOTCORR en mm/jour, T2M en degres C), point central de chaque region.",
           "source": "NASA POWER, https://power.larc.nasa.gov/", "regions": out}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "climate.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print(f"\n{len(out)}/{len(REGIONS)} regions. Ecrit : {path}")
    print(f"{'Region':34} {'pluie an. mm':>13} {'T moy C':>8}")
    for name, r in out.items():
        rain = sum(r['rain_mm_day'][m] * d for m, d in zip(MONTHS, (31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)))
        print(f"{name:34} {rain:13.0f} {sum(r['temp_c'].values()) / 12:8.1f}")


if __name__ == "__main__":
    main()