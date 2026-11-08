"""SEO and open-data harvester discoverability: Sitemap XML, schema.org/Dataset JSON-LD, and DCAT-AP."""
from __future__ import annotations

import base64
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from app.services.storage import SECTOR_IDS

# 16x16 + 32x32 multi-resolution ICO and 32x32 PNG matching the official FreeData.td "FD" logo (#2563eb)
FAVICON_ICO: bytes = base64.b64decode(
    "AAABAAIAEBAAAAEAIABAAQAAJgAAACAgAAABACAAJwIAAGYBAACJUE5HDQoaCgAAAA1JSERSAAAAEAAAABAIBgAAAB/z/2EAAAAB"
    "c1JHQgCuzhzpAAAABGdBTUEAALGPC/xhBQAAAAlwSFlzAAAOwwAADsMBx2+oZAAAANVJREFUOE9jYGBgYJCPv8+hmvy6QTXp1X7V"
    "5Nf/8WKQmpQ37fLx7wVAesGaVZJen8dQSBg/l49/KcGgmvy6H4skUVgl+fVyBjJth+JX70EuwCJBPKauAQ1LPv+HARAbmb/q0Pf/"
    "rlXvCBuw6+xPrPw5O76BDSFoAAiANIFsQzYgsOk9WI6gAbhc0LvuK3EuQDcABkDiVkVv8RtADmZQSX59H12QBPwdZMByLBLE4aRX"
    "+xnU458rgEzCkCQCKye/dgDnSLX41xpEZWUYTnp9XDn5pQdILwANAX4VMAPy4gAAAABJRU5ErkJggolQTkcNChoKAAAADUlIRFIA"
    "AAAgAAAAIAgGAAAAc3p69AAAAAFzUkdCAK7OHOkAAAAEZ0FNQQAAsY8L/GEFAAAACXBIWXMAAA7DAAAOwwHHb6hkAAABvElEQVRY"
    "R+2XsUsDMRTGMzo6ulVoTt1cxclFcPUvOHvpUJxEHMRJXJykg6ODi5ODjoKL4OKiuLt0bO9SPVSkKELlO03JJblewFxcfPBb8qXv"
    "ffderlwIUaIWppNBFK8FjLeDKLkKGB/+iu8cbeSshfGUWi8XdcaXAsa7WhJnJCmMqHWzoI14W/9BNVDWP88V/3lybWOV0KjXyopn"
    "M6+07YUMZsPuNKGNZMMg+qHZ3yeU8WNN8EXELwiN+L0meCNJib7ol38DpQZW91KN5Z2nQm1+va/lGEepAVNc3r0XaojT68FwcfNR"
    "y2XC2sDtw0dWGBycvRm1Tu9ztIaw6Ya1AbTXRmsdPo/Wt45etN+oWBtAMjFn0V4RqjmMACFGNQ5rA3LsnrzmNNUAdIRTA/IZQJtl"
    "TTWAM+LcgFqkSMPBEyEO6zicGBDnA52R3wSbV9GJAVOIP6sySg2IuZsSCk0G3bB5/wWlBqrm7w1QxjvqokcGBJ/IBsEPEb/xeh8w"
    "0CYzIZ9DKwxi5dRZvOL9ViTA13judoR5qJuqAgcfF6KcgVrYmcBFQd3sGjy5VlwO2uwtYJPL+wJyIedo5lJ8AYA5399Rqit/AAAA"
    "AElFTkSuQmCC"
)

FAVICON_PNG: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAG8SURBVFhH"
    "7ZexSwMxFMYzOjq6VWhO3VzFyUVw9S84e+lQnEQcxElcnKSDo4OLk4OOgovg4qK4u3Rs71I9VKQoQuU7TckluV7AXFx88Fvype99916uXAhRohamk0EUrwWMt4Mo"
    "uQoYH/6K7xxt5KyF8ZRaLxd1xpcCxrtaEmckKYyodbOgjXhb/0E1UNY/zxX/eXJtY5XQqNfKimczr7TthQxmw+40oY1kwyD6odnfJ5TxY03wRcQvCI34vSZ4I0mJ"
    "vuiXfwOlBlb3Uo3lnadCbX69r+UYR6kBU1zevRdqiNPrwXBx81HLZcLawO3DR1YYHJy9GbVO73O0hrDphrUBtNdGax0+j9a3jl6036hYG0AyMWfRXhGqOYwAIUY1"
    "DmsDcuyevOY01QB0hFMD8hlAm2VNNYAz4tyAWqRIw8ETIQ7rOJwYEOcDnZHfBJtX0YkBU4g/qzJKDYi5mxIKTQbdsHn/BaUGqubvDVDGO+qiRwYEn8gGwQ8Rv/F6"
    "HzDQJjMhn0MrDGLl1Fm84v1WJMDXeO52hHmom6oCBx8XopyBWtiZwEVB3ewaPLlWXA7a7C1gk8v7AnIh52jmUnwBgDnf31GqK38AAAAASUVORK5CYII="
)

CC_BY_40_URL = "https://creativecommons.org/licenses/by/4.0/"


def _in_fd_glyph(u: float, v: float) -> bool:
    """True when (u, v) in a 32x32 coordinate space lies inside the bold 'FD' monogram."""
    if not (10.6 <= v <= 21.4):
        return False
    # Letter F
    if 7.6 <= u <= 10.1:
        return True
    if 7.6 <= u <= 14.8 and 10.6 <= v <= 12.75:
        return True
    if 7.6 <= u <= 14.25 and 15.1 <= v <= 17.2:
        return True
    # Letter D
    if u < 16.4:
        return False
    in_outer = u <= 20.4 or ((u - 20.4) / 4.4) ** 2 + ((v - 16.0) / 5.4) ** 2 <= 1.0
    if not in_outer:
        return False
    in_hole = (
        u >= 18.9
        and 12.75 <= v <= 19.25
        and (u <= 20.2 or ((u - 20.2) / 2.1) ** 2 + ((v - 16.0) / 3.25) ** 2 <= 1.0)
    )
    return not in_hole


def _encode_fd_png(size: int, *, maskable: bool = False) -> bytes:
    """Generate a valid RGBA PNG of the official FreeData.td 'FD' icon at `size`x`size`."""
    blue = b"\x25\x63\xeb\xff"
    white = b"\xff\xff\xff\xff"
    transparent = b"\x00\x00\x00\x00"
    scale = 32.0 / size
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # PNG filter type 0 (None)
        v = (py + 0.5) * scale
        if maskable:
            # Maskable icons keep the monogram inside the central 80% safe zone on a full blue canvas
            v_glyph = (v - 16.0) * 1.2 + 16.0
            for px in range(size):
                u_glyph = ((px + 0.5) * scale - 16.0) * 1.2 + 16.0
                rows.extend(white if _in_fd_glyph(u_glyph, v_glyph) else blue)
        else:
            dy = max(abs(v - 16.0) - 8.0, 0.0)
            dy2 = dy * dy
            for px in range(size):
                u = (px + 0.5) * scale
                dx = max(abs(u - 16.0) - 8.0, 0.0)
                if dx * dx + dy2 > 64.0:
                    rows.extend(transparent)
                elif _in_fd_glyph(u, v):
                    rows.extend(white)
                else:
                    rows.extend(blue)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(rows), level=6))
        + _chunk(b"IEND", b"")
    )


ICON_192_PNG: bytes = _encode_fd_png(192, maskable=False)
ICON_512_PNG: bytes = _encode_fd_png(512, maskable=False)
ICON_MASKABLE_512_PNG: bytes = _encode_fd_png(512, maskable=True)


def _sync_static_favicon_files() -> None:
    """Ensure on-disk favicon/PWA icons in app/static hold the binary bytes when writable."""
    static_dir = Path(__file__).resolve().parents[1] / "static"
    for name, payload in (
        ("favicon.ico", FAVICON_ICO),
        ("favicon.png", FAVICON_PNG),
        ("apple-touch-icon.png", ICON_192_PNG),
        ("icon-192.png", ICON_192_PNG),
        ("icon-512.png", ICON_512_PNG),
        ("icon-maskable-512.png", ICON_MASKABLE_512_PNG),
    ):
        target = static_dir / name
        try:
            if not target.exists() or target.stat().st_size < len(payload):
                target.write_bytes(payload)
        except OSError:
            pass


_sync_static_favicon_files()

SECTOR_METADATA: dict[str, dict[str, Any]] = {
    "agriculture": {
        "title": "Agriculture & Production Vivrière au Tchad (Chad Agriculture Dataset)",
        "description": (
            "Séries temporelles sur la production agricole, les rendements céréaliers, les terres arables "
            "et l'agrométéorologie au Tchad (World Bank, FAOSTAT, NASA POWER, Open-Meteo)."
        ),
        "keywords": ["Tchad", "Chad", "agriculture", "céréales", "rendements", "FAOSTAT", "World Bank"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/AGRI",
    },
    "environment": {
        "title": "Climat, Météorologie & Environnement au Tchad (Chad Climate & Environment Dataset)",
        "description": (
            "Observations météorologiques, précipitations, températures, rayonnement solaire et feux actifs "
            "par province au Tchad (Open-Meteo, NASA POWER, NASA FIRMS)."
        ),
        "keywords": ["Tchad", "Chad", "climat", "météo", "précipitations", "température", "environnement"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/ENVI",
    },
    "markets": {
        "title": "Prix des Marchés & Sécurité Alimentaire au Tchad (Chad Market Prices Dataset)",
        "description": (
            "Prix de détail et de gros des denrées alimentaires (mil, sorgho, maïs, riz, arachide, bétail) "
            "sur les marchés du Tchad et inflation alimentaire (FEWS NET, PAM/WFP HDX, FAOSTAT)."
        ),
        "keywords": ["Tchad", "Chad", "marchés", "prix alimentaires", "mil", "sorgho", "FEWS NET", "WFP"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/ECON",
    },
    "economy": {
        "title": "Indicateurs Macroéconomiques du Tchad (Chad Macroeconomic Dataset)",
        "description": (
            "PIB, croissance économique, inflation, dette publique, commerce extérieur et balance des "
            "paiements du Tchad (Banque mondiale WDI, FMI World Economic Outlook)."
        ),
        "keywords": ["Tchad", "Chad", "économie", "PIB", "inflation", "FMI", "IMF", "World Bank"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/ECON",
    },
    "health": {
        "title": "Santé Publique & Infrastructures Sanitaires au Tchad (Chad Health Dataset)",
        "description": (
            "Indicateurs de santé publique, espérance de vie, mortalité infantile, vaccination et "
            "cartographie des infrastructures sanitaires par province au Tchad (World Bank, OpenStreetMap)."
        ),
        "keywords": ["Tchad", "Chad", "santé", "hôpitaux", "espérance de vie", "mortalité", "vaccination"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/HEAL",
    },
    "energy": {
        "title": "Accès à l'Énergie & Électrification au Tchad (Chad Energy Dataset)",
        "description": (
            "Taux d'accès à l'électricité (urbain, rural, national), énergies renouvelables et "
            "consommation énergétique au Tchad (Banque mondiale)."
        ),
        "keywords": ["Tchad", "Chad", "énergie", "électricité", "énergies renouvelables"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/ENER",
    },
    "transport": {
        "title": "Transports & Infrastructures Aéroportuaires au Tchad (Chad Transport Dataset)",
        "description": (
            "Aéroports, aérodromes, pistes et indicateurs logistiques et météorologiques de transport "
            "au Tchad (OurAirports, Open-Meteo, Banque mondiale)."
        ),
        "keywords": ["Tchad", "Chad", "transports", "aéroports", "infrastructures", "logistique"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/TRAN",
    },
    "education": {
        "title": "Éducation, Scolarisation & Établissements au Tchad (Chad Education Dataset)",
        "description": (
            "Taux d'alphabétisation, scolarisation primaire et secondaire, parité et localisation des "
            "établissements scolaires par région au Tchad (UNESCO UIS, UNICEF, OpenStreetMap, Banque mondiale)."
        ),
        "keywords": ["Tchad", "Chad", "éducation", "scolarisation", "alphabétisation", "UNESCO", "UNICEF"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/EDUC",
    },
    "demography": {
        "title": "Démographie, Population & Réfugiés au Tchad (Chad Demography Dataset)",
        "description": (
            "Population totale, répartition par âge, sexe et milieu de résidence, urbanisation, fécondité "
            "et populations déplacées au Tchad (INSEED, Banque mondiale WDI, HCR/UNHCR)."
        ),
        "keywords": ["Tchad", "Chad", "démographie", "population", "INSEED", "UNHCR", "recensement"],
        "theme": "http://publications.europa.eu/resource/authority/data-theme/SOCI",
    },
}


def _iso_date(raw: str | None) -> str:
    if raw and len(str(raw)) >= 10:
        part = str(raw)[:10]
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _sector_catalog_summary(catalog_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_sector: dict[str, dict[str, Any]] = {
        sec: {"indicators": set(), "sources": set(), "records": 0, "first_date": None, "last_date": None}
        for sec in SECTOR_IDS
    }
    for row in catalog_rows:
        sec = str(row.get("sector") or "")
        if sec not in by_sector:
            continue
        entry = by_sector[sec]
        if row.get("indicator"):
            entry["indicators"].add(str(row["indicator"]))
        if row.get("source"):
            entry["sources"].add(str(row["source"]))
        entry["records"] += int(row.get("records") or 0)
        f_date = str(row.get("first_date") or "")[:10]
        l_date = str(row.get("last_date") or "")[:10]
        if f_date and (entry["first_date"] is None or f_date < entry["first_date"]):
            entry["first_date"] = f_date
        if l_date and (entry["last_date"] is None or l_date > entry["last_date"]):
            entry["last_date"] = l_date
    return by_sector


def _distributions_schema_org(base_url: str, sector: str | None = None) -> list[dict[str, Any]]:
    query = f"?sector={sector}" if sector else ""
    items = [
        ("CSV", "text/csv", f"{base_url}/api/v1/export/csv{query}"),
        ("JSON", "application/json", f"{base_url}/api/v1/export/json{query}"),
        ("XML", "application/xml", f"{base_url}/api/v1/export/xml{query}"),
        ("Parquet", "application/vnd.apache.parquet", f"{base_url}/api/v1/export/parquet{query}"),
    ]
    return [
        {
            "@type": "DataDownload",
            "name": f"FreeData.td {sector or 'all'} ({label})",
            "encodingFormat": media_type,
            "contentUrl": url,
            "license": CC_BY_40_URL,
        }
        for label, media_type, url in items
    ]


def _distributions_dcat(base_url: str, sector: str | None = None) -> list[dict[str, Any]]:
    query = f"?sector={sector}" if sector else ""
    items = [
        ("CSV", "text/csv", f"{base_url}/api/v1/export/csv{query}"),
        ("JSON", "application/json", f"{base_url}/api/v1/export/json{query}"),
        ("XML", "application/xml", f"{base_url}/api/v1/export/xml{query}"),
        ("PARQUET", "application/vnd.apache.parquet", f"{base_url}/api/v1/export/parquet{query}"),
    ]
    return [
        {
            "@type": "dcat:Distribution",
            "dct:title": f"FreeData.td — {sector or 'all'} ({fmt})",
            "dct:format": fmt,
            "dcat:mediaType": media_type,
            "dcat:downloadURL": url,
            "dcat:accessURL": f"{base_url}/",
            "dct:license": CC_BY_40_URL,
        }
        for fmt, media_type, url in items
    ]


def build_schema_org_catalog(
    base_url: str,
    catalog_rows: list[dict[str, Any]],
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Build a schema.org/DataCatalog + Dataset JSON-LD document for Google Dataset Search & harvesters."""
    base = base_url.rstrip("/")
    summary = _sector_catalog_summary(catalog_rows)
    sector_counts = (stats or {}).get("sectors") or {}
    last_mod = _iso_date((stats or {}).get("last_update"))

    datasets: list[dict[str, Any]] = []
    for sec in SECTOR_IDS:
        meta = SECTOR_METADATA.get(sec, {})
        sec_info = summary.get(sec, {})
        obs_count = int(sector_counts.get(sec) or sec_info.get("records") or 0)
        sources = sorted(sec_info.get("sources") or [])
        indicators = sorted(sec_info.get("indicators") or [])
        first_date = sec_info.get("first_date")
        last_date = sec_info.get("last_date")

        ds: dict[str, Any] = {
            "@type": "Dataset",
            "@id": f"{base}/api/v1/catalog.jsonld#dataset-{sec}",
            "identifier": f"freedatatd-{sec}",
            "name": meta.get("title", f"FreeData.td — {sec}"),
            "description": meta.get("description", f"Open socioeconomic dataset for {sec} in Chad."),
            "url": f"{base}/api/v1/observations?sector={sec}",
            "sameAs": f"{base}/#/data?sector={sec}",
            "license": CC_BY_40_URL,
            "isAccessibleForFree": True,
            "inLanguage": ["fr", "en"],
            "keywords": meta.get("keywords", ["Tchad", "Chad", sec]),
            "creator": {
                "@type": "Organization",
                "name": "FreeData.td",
                "url": f"{base}/",
            },
            "spatialCoverage": {
                "@type": "Place",
                "name": "Chad (Tchad)",
                "geo": {"@type": "GeoShape", "addressCountry": "TD"},
            },
            "dateModified": last_mod,
            "distribution": _distributions_schema_org(base, sec),
            "variableMeasured": indicators[:50],
        }
        if first_date and last_date:
            ds["temporalCoverage"] = f"{first_date}/{last_date}"
        if sources:
            ds["isBasedOn"] = sources
        if obs_count:
            ds["size"] = f"{obs_count} observations"
        datasets.append(ds)

    return {
        "@context": "https://schema.org",
        "@type": "DataCatalog",
        "@id": f"{base}/api/v1/catalog.jsonld",
        "name": "FreeData.td — Infrastructure de Données Ouvertes pour le Tchad",
        "alternateName": "FreeData.td Open Data Catalog for Chad",
        "description": (
            "Catalogue ouvert de données socioéconomiques, agricoles, climatiques, sanitaires et "
            "démographiques de la République du Tchad."
        ),
        "url": f"{base}/",
        "license": CC_BY_40_URL,
        "inLanguage": ["fr", "en"],
        "dateModified": last_mod,
        "publisher": {
            "@type": "Organization",
            "name": "FreeData.td",
            "url": f"{base}/",
        },
        "dataset": datasets,
    }


def build_dcat_ap_catalog(
    base_url: str,
    catalog_rows: list[dict[str, Any]],
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Build a DCAT-AP compliant JSON-LD catalogue for HDX, OpenDataSoft, CKAN and institutional harvesters."""
    base = base_url.rstrip("/")
    summary = _sector_catalog_summary(catalog_rows)
    sector_counts = (stats or {}).get("sectors") or {}
    last_mod = _iso_date((stats or {}).get("last_update"))

    datasets: list[dict[str, Any]] = []
    for sec in SECTOR_IDS:
        meta = SECTOR_METADATA.get(sec, {})
        sec_info = summary.get(sec, {})
        obs_count = int(sector_counts.get(sec) or sec_info.get("records") or 0)
        first_date = sec_info.get("first_date")
        last_date = sec_info.get("last_date")

        ds: dict[str, Any] = {
            "@type": "dcat:Dataset",
            "@id": f"{base}/api/v1/catalog.dcat.json#dataset-{sec}",
            "dct:identifier": f"freedatatd-{sec}",
            "dct:title": meta.get("title", f"FreeData.td — {sec}"),
            "dct:description": meta.get("description", f"Open socioeconomic dataset for {sec} in Chad."),
            "dcat:landingPage": f"{base}/",
            "dct:language": ["fr", "en"],
            "dct:license": CC_BY_40_URL,
            "dct:modified": last_mod,
            "dct:accrualPeriodicity": "http://publications.europa.eu/resource/authority/frequency/DAILY",
            "dct:spatial": {
                "@type": "dct:Location",
                "rdfs:label": "Chad (TCD)",
            },
            "dct:publisher": {
                "@type": "foaf:Organization",
                "foaf:name": "FreeData.td",
                "foaf:homepage": f"{base}/",
            },
            "dcat:keyword": meta.get("keywords", ["Tchad", "Chad", sec]),
            "dcat:theme": [{"@id": meta["theme"]}] if meta.get("theme") else [],
            "dcat:distribution": _distributions_dcat(base, sec),
        }
        if first_date and last_date:
            ds["dct:temporal"] = {
                "@type": "dct:PeriodOfTime",
                "dcat:startDate": first_date,
                "dcat:endDate": last_date,
            }
        if obs_count:
            ds["dct:extent"] = f"{obs_count} observations"
        datasets.append(ds)

    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "foaf": "http://xmlns.com/foaf/0.1/",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
        "@type": "dcat:Catalog",
        "@id": f"{base}/api/v1/catalog.dcat.json",
        "dct:title": "FreeData.td — Open Data Infrastructure for Chad",
        "dct:description": (
            "Catalogue ouvert DCAT-AP des jeux de données socioéconomiques du Tchad "
            "(agriculture, marchés, climat, économie, santé, énergie, transports, éducation, démographie)."
        ),
        "foaf:homepage": f"{base}/",
        "dct:license": CC_BY_40_URL,
        "dct:language": ["fr", "en"],
        "dct:modified": last_mod,
        "dct:spatial": {"@type": "dct:Location", "rdfs:label": "Chad (TCD)"},
        "dct:publisher": {
            "@type": "foaf:Organization",
            "foaf:name": "FreeData.td",
            "foaf:homepage": f"{base}/",
        },
        "dcat:dataset": datasets,
    }


def build_sitemap_xml(base_url: str, stats: dict[str, Any] | None = None) -> str:
    """Build a static/crawlable XML sitemap listing the portal, documentation, metadata feeds, and sector datasets."""
    base = base_url.rstrip("/")
    last_mod = _iso_date((stats or {}).get("last_update"))

    entries: list[tuple[str, str, str]] = [
        (f"{base}/", "daily", "1.0"),
        (f"{base}/api/v1/catalog.jsonld", "daily", "0.9"),
        (f"{base}/api/v1/catalog.dcat.json", "daily", "0.9"),
        (f"{base}/api/v1/catalog", "daily", "0.8"),
        (f"{base}/docs", "weekly", "0.7"),
    ]
    for sec in SECTOR_IDS:
        entries.append((f"{base}/api/v1/observations?sector={sec}", "daily", "0.8"))
        entries.append((f"{base}/api/v1/export/csv?sector={sec}", "daily", "0.8"))
        entries.append((f"{base}/api/v1/export/json?sector={sec}", "daily", "0.7"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, freq, prio in entries:
        lines.extend([
            "  <url>",
            f"    <loc>{xml_escape(loc)}</loc>",
            f"    <lastmod>{last_mod}</lastmod>",
            f"    <changefreq>{freq}</changefreq>",
            f"    <priority>{prio}</priority>",
            "  </url>",
        ])
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"

