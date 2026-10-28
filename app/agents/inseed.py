"""Official statistics of Chad's national statistics institute (INSEED), read from SDMX files.

The INSEED open-data portal (chad.opendataforafrica.org) publishes its "Principaux indicateurs
statistiques" through an SDMX API that sits behind a Cloudflare bot challenge. We never try to get
around that challenge: the administrator downloads the answers from his own machine (or INSEED
gives the platform an access key later) and this module turns the saved SDMX-ML files into
observations, per province where INSEED provides it.

Licence: INSEED Open Licence Agreement. Reuse, also commercial, is allowed; the notice below must
stay on the data ("Source : INSEED. Contient des informations sous licence selon l'Accord de
Licence Ouverte de l'INSEED.").
"""
from __future__ import annotations

import logging
import re
from xml.etree.ElementTree import ParseError  # noqa: S405 - only the exception type, parsing is done by defusedxml
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET

from app.agents.base import BaseAgent
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)

SOURCE_LABEL = "INSEED"
LICENSE = "Licence Ouverte INSEED"
# The French sentence is the wording required by the licence; the English line is a courtesy translation.
ATTRIBUTION = ("Source : INSEED. Contient des informations sous licence selon l'Accord de Licence Ouverte de l'INSEED. "
               "(Source: INSEED. Contains information licensed under the INSEED Open Licence Agreement.)")
PORTAL_URL = "https://chad.opendataforafrica.org/tylheoe/principaux-indicateurs-statistiques"


@dataclass(frozen=True)
class Dataset:
    flow: str       # SDMX dataflow id, also the file name: inseed_<flow>.xml
    label: str      # indicator name shown to users
    sector: str
    unit: str
    key: str        # the request, exactly as written on the INSEED page


# Only datasets whose real answer has been seen are registered: add the others one by one.
DATASETS: dict[str, Dataset] = {d.flow: d for d in (
    Dataset("urtpzwb", "Health facilities", "health", "facilities",
            "TD+TD-BA+TD-BO+TD-CB+TD-GR+TD-HL+TD-KA+TD-LC+TD-LO+TD-LR+TD-MA+TD-MO+TD-ME+TD-MC+TD-OD+TD-SA+TD-TA+TD-WF+TD-ND"
            "+TD-BG+TD-EO+TD-SI+TD-TI+TD-EE.PUB+PRV.HN+HP+HD+CS+CLI+CAM+CAS.TOT"),
    # National only (no province in this table).
    Dataset("pqvhyxg", "Population", "demography", "inhabitants",
            "POPT+P0_4+P5_9+P10_14+P15_19+P20_24+P25_29+P30_34+P35_39+P40_44+P45_49+P50_54+P55_59+P60_64"
            "+P65_69+P70_74+P75_79+P80_P.M+F.U+R"),
    Dataset("xxhsxif", "Consumer price index", "economy", "index",
            "PCPI_IX+PCPI_CP_01_IX+PCPI_CP_02_IX+PCPI_CP_03_IX+PCPI_CP_04_IX+PCPI_CP_05_IX+PCPI_CP_06_IX"
            "+PCPI_CP_07_IX+PCPI_CP_08_IX+PCPI_CP_09_IX+PCPI_CP_10_IX+PCPI_CP_11_IX.2019"),
)}

# ISO 3166-2:TD province codes -> the region names already used elsewhere in the platform.
PROVINCES = {
    "TD": "national", "TD-BA": "Batha", "TD-BG": "Barh el Gazel", "TD-BO": "Borkou", "TD-CB": "Chari-Baguirmi",
    "TD-EE": "Ennedi Est", "TD-EO": "Ennedi Ouest", "TD-GR": "Guera", "TD-HL": "Hadjer-Lamis", "TD-KA": "Kanem",
    "TD-LC": "Lac", "TD-LO": "Logone Occidental", "TD-LR": "Logone Oriental", "TD-MA": "Mandoul",
    "TD-MC": "Moyen-Chari", "TD-ME": "Mayo-Kebbi Est", "TD-MO": "Mayo-Kebbi Ouest", "TD-ND": "N'Djamena",
    "TD-OD": "Ouaddai", "TD-SA": "Salamat", "TD-SI": "Sila", "TD-TA": "Tandjile", "TD-TI": "Tibesti",
    "TD-WF": "Wadi Fira",
}
# Indicator names are English, like every other source of the platform (the interface itself is
# bilingual). Only codes whose meaning is certain are translated; any other code is shown as is.
CODE_LABELS = {
    "PUB": "public", "PRV": "private", "COM": "community",
    "HN": "national hospital", "HP": "provincial hospital", "HD": "district hospital",
    "CS": "health centre", "CLI": "clinic",
    "M": "men", "F": "women", "U": "urban", "R": "rural", "POPT": "all ages",
    "PCPI_IX": "all items", "PCPI_CP_01_IX": "food and non-alcoholic beverages",
}
_AGE_GROUP = re.compile(r"^P(\d{1,2})_(\d{1,2})$")
_AGE_OPEN = re.compile(r"^P(\d{2})_P$")


def code_label(code: str) -> str:
    """Readable form of an INSEED code: known labels, age groups (P5_9 -> 5-9 years), else the code."""
    if code in CODE_LABELS:
        return CODE_LABELS[code]
    m = _AGE_GROUP.match(code)
    if m:
        return f"{m[1]}-{m[2]} years"
    m = _AGE_OPEN.match(code)
    if m:
        return f"{m[1]} years and over"
    return code


_PROVINCE_CODE = re.compile(r"^TD(-[A-Z]{2})?$")
_SKIPPED_ATTRIBUTES = ("ID_", "REGIONID_")
_IGNORED_VALUES = {"TOT"}          # "total" adds nothing to an indicator name


def parse_period(text: str) -> tuple[int, int, int] | None:
    """(year, month, day) from the SDMX forms 2024, 2024-03, 2024-M03, 2024-Q2, 2024-03-15."""
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        return int(m[1]), 1, 1
    m = re.fullmatch(r"(\d{4})-?M?(\d{1,2})", t)
    if m and 1 <= int(m[2]) <= 12:
        return int(m[1]), int(m[2]), 1
    m = re.fullmatch(r"(\d{4})-?Q([1-4])", t)
    if m:
        return int(m[1]), 3 * int(m[2]) - 2, 1
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
        return int(m[1]), int(m[2]), int(m[3])
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sdmx(xml_text: str, dataset: Dataset) -> list[dict[str, Any]]:
    """SDMX-ML (StructureSpecificData) -> one record per observation, in the form that
    InseedAgent.normalize understands. Unreadable observations are skipped, not guessed."""
    upper = xml_text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise ValueError("refused: the document declares a DOCTYPE/ENTITY (possible entity-expansion attack)")
    try:
        root = SafeET.fromstring(xml_text)   # defusedxml: no entity expansion, no external references
    except ParseError as exc:
        raise ValueError(f"not a valid XML document: {exc}") from exc

    records: list[dict[str, Any]] = []
    for series in (e for e in root.iter() if _local(e.tag) == "Series"):
        attrs = dict(series.attrib)
        region_code = next((v for k, v in attrs.items()
                            if not k.startswith(_SKIPPED_ATTRIBUTES) and _PROVINCE_CODE.match(v)), "TD")
        parts = []
        for name, value in attrs.items():
            if name == "FREQ" or name.startswith(_SKIPPED_ATTRIBUTES) or value == region_code or value in _IGNORED_VALUES:
                continue
            parts.append(code_label(value))
        base = dataset.label + (" - " + ", ".join(parts) if parts else "")
        for obs in (e for e in series if _local(e.tag) == "Obs"):
            when = parse_period(obs.attrib.get("TIME_PERIOD", ""))
            raw = (obs.attrib.get("OBS_VALUE") or "").strip()
            if not when or not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if value != value:       # NaN
                continue
            # A figure for a year that has not happened yet is a projection: keep it apart so a
            # forecast is never read as a measurement of that indicator.
            indicator = base + (" (projection)" if when[0] > date.today().year else "")
            records.append({
                "year": when[0], "month": when[1], "day": when[2], "value": value,
                "indicator": indicator[:120], "unit": dataset.unit, "sector": dataset.sector,
                "region": PROVINCES.get(region_code, region_code),
            })
    return records


def load_files(paths: list[Path]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Read saved answers named inseed_<flow>.xml -> ({sector: records}, problems)."""
    by_sector: dict[str, list[dict[str, Any]]] = {}
    problems: list[str] = []
    for path in paths:
        m = re.fullmatch(r"inseed_([a-z0-9]+)\.xml", path.name)
        dataset = DATASETS.get(m[1]) if m else None
        if dataset is None:
            problems.append(f"{path.name}: unknown dataset (known: {', '.join(sorted(DATASETS))})")
            continue
        try:
            records = parse_sdmx(path.read_text(encoding="utf-8"), dataset)
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        if not records:
            problems.append(f"{path.name}: no observation found")
        by_sector.setdefault(dataset.sector, []).extend(records)
    return by_sector, problems


class InseedAgent(BaseAgent):
    """Runs INSEED records of ONE sector through the standard pipeline (validation, data-science
    rules, raw archive, upsert). The sector is chosen per instance because INSEED covers several."""

    name = "InseedAgent"

    def __init__(self, repository, sector: str, records: list[dict[str, Any]]) -> None:
        super().__init__(repository)
        self.sector = sector
        self._records = records

    async def collect(self, source: str) -> list[dict[str, Any]]:
        return list(self._records)

    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None
        val = float(record["value"])
        return ObservationCreate(
            sector=self.sector,
            indicator=str(record["indicator"]),
            value=val if val.is_integer() else round(val, 2),
            unit=str(record["unit"])[:30],
            reference_date=date(int(record["year"]), int(record.get("month", 1)), int(record.get("day", 1))),
            region=str(record.get("region", "national"))[:50],
            source=SOURCE_LABEL,
            source_url=PORTAL_URL,
            license=LICENSE,
            notes=ATTRIBUTION,
        )
