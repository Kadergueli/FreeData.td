from __future__ import annotations

from datetime import date
import logging
from typing import Any

import httpx

import asyncio

from app.agents.base import BaseAgent, source_terms, wb_years
from app.agents.dhs import DHS_INDICATORS, DHS_URL, MAX_PAGES, PAGE, parse_dhs
from app.agents.osm import HOSPITALS, PHARMACIES, WATER_POINTS, collect_osm_counts
from app.agents.unicef import collect_unicef
from app.agents.who_gho import GHO_INDICATORS, GHO_URL, describe_rows, parse_gho
from app.schemas import ObservationCreate

logger = logging.getLogger(__name__)


class HealthAgent(BaseAgent):
    """Collects public health indicators for Chad: World Bank (WDI), WHO Global Health Observatory
    (OData API, checked live in Nov 2026), DHS Program survey indicators by region, UNICEF
    nutrition and immunisation, and OpenStreetMap health facilities."""

    sector = "health"
    name = "HealthAgent"

    # code -> (indicator name, unit). Units stay under 40 characters (normalize() truncates).
    # Fertility, birth and death rates live in DemographyAgent: not repeated here.
    WORLD_BANK_INDICATORS = {
        # Existing series
        "SP.DYN.LE00.IN": ("Life expectancy at birth", "years"),
        "SH.DYN.MORT": ("Under-5 mortality rate", "per 1,000 live births"),
        "SH.STA.MMRT": ("Maternal mortality ratio", "per 100,000 live births"),
        "SH.XPD.CHEX.GD.ZS": ("Current health expenditure", "% of GDP"),
        "SH.STA.BRTC.ZS": ("Births attended by skilled health staff", "% of total"),
        "SH.STA.STNT.ZS": ("Stunting prevalence, children under 5", "% of children under 5"),
        "SH.H2O.BASW.ZS": ("Access to basic drinking water services", "% of population"),
        "SH.STA.BASS.ZS": ("Access to basic sanitation services", "% of population"),
        # Child and maternal health
        "SH.DYN.NMRT": ("Neonatal mortality rate", "per 1,000 live births"),
        "SP.DYN.IMRT.IN": ("Infant mortality rate", "per 1,000 live births"),
        "SH.STA.WAST.ZS": ("Wasting prevalence, children under 5", "% of children under 5"),
        "SH.PRG.ANEM": ("Anemia prevalence, pregnant women", "% of pregnant women"),
        "SH.STA.ANVC.ZS": ("Prenatal care coverage", "% of pregnant women"),
        # Immunization
        "SH.IMM.MEAS": ("Measles immunization, children 12-23 months", "% of children 12-23 months"),
        "SH.IMM.IDPT": ("DPT immunization, children 12-23 months", "% of children 12-23 months"),
        "SH.IMM.HEPB": ("Hepatitis B immunization, children 12-23 months", "% of children 12-23 months"),
        # Infectious diseases
        "SH.MLR.INCD.P3": ("Malaria incidence", "per 1,000 population at risk"),
        "SH.MLR.NETS.ZS": ("Insecticide-treated bed net use, children under 5", "% of children under 5"),
        "SH.TBS.INCD": ("Tuberculosis incidence", "per 100,000 people"),
        "SH.TBS.DTEC.ZS": ("Tuberculosis case detection rate", "% of estimated cases"),
        "SH.HIV.INCD.ZS": ("HIV incidence, ages 15-49", "per 1,000 uninfected, ages 15-49"),
        "SH.DYN.AIDS.ZS": ("HIV prevalence, ages 15-49", "% of population ages 15-49"),
        # Health system and nutrition
        "SH.MED.PHYS.ZS": ("Physicians", "per 1,000 people"),
        "SH.MED.NUMW.P3": ("Nurses and midwives", "per 1,000 people"),
        "SH.MED.BEDS.ZS": ("Hospital beds", "per 1,000 people"),
        "SH.XPD.OOPC.CH.ZS": ("Out-of-pocket health expenditure", "% of current health expenditure"),
        "SN.ITK.DEFC.ZS": ("Prevalence of undernourishment", "% of population"),
        "SH.STA.OWAD.ZS": ("Overweight prevalence, adults", "% of adults"),
        "SH.H2O.SMDW.ZS": ("Safely managed drinking water", "% of population"),
        "SP.DYN.CONU.ZS": ("Contraceptive prevalence, any method", "% of married women 15-49"),
    }

    # ISO3 for Chad
    CHAD_ISO3 = "TCD"

    async def collect(self, source: str) -> list[dict[str, Any]]:
        if source == "demo":
            return self._get_demo_records()

        if source == "world-bank":
            return await self._collect_world_bank()

        if source == "open-street-map":
            return await self._collect_open_street_map()

        if source == "who-gho":
            return await self._collect_who_gho()

        if source == "dhs":
            return await self._collect_dhs()

        if source == "unicef":
            return await self._collect_unicef()

        if source in ("all", "auto"):
            names = ("world-bank", "who-gho", "dhs", "unicef", "open-street-map")
            results = await asyncio.gather(
                self._collect_world_bank(), self._collect_who_gho(), self._collect_dhs(),
                self._collect_unicef(), self._collect_open_street_map(), return_exceptions=True)
            combined: list[dict[str, Any]] = []
            for name, res in zip(names, results):
                if isinstance(res, list):
                    combined.extend(res)
                elif isinstance(res, Exception):
                    logger.error("HealthAgent source %s failed: %s", name, res)
                    self.note_source_failure(name, res)
            return combined

        raise ValueError(f"Unknown source '{source}'. Supported: 'all', 'world-bank', 'who-gho', 'dhs', 'unicef', 'open-street-map', 'demo'.")

    async def _collect_who_gho(self) -> list[dict[str, Any]]:
        """WHO Global Health Observatory series for Chad. One indicator failing is listed in the run
        errors without hiding the others; nothing at all raises so the run reports the failure."""
        records: list[dict[str, Any]] = []
        failed: list[str] = []
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for code in GHO_INDICATORS:
                reason: list[str] = []
                payload = await self.fetch_json_with_retry(
                    client, f"{GHO_URL}/{code}", params={"$filter": f"SpatialDim eq '{self.CHAD_ISO3}'"},
                    throttle_seconds=0.2, errors=reason)
                parsed = parse_gho(payload, code) if payload is not None else []
                if parsed:
                    records.extend(parsed)
                else:
                    failed.append(f"{code} ({reason[0] if reason else describe_rows(payload)})")
        if failed:
            self.source_errors.append(f"WHO GHO: {len(failed)}/{len(GHO_INDICATORS)} series empty: {'; '.join(failed[:4])}")
        if not records:
            raise RuntimeError("WHO GHO returned nothing")
        return records

    async def _collect_unicef(self) -> list[dict[str, Any]]:
        """UNICEF nutrition (stunting, wasting, breastfeeding...) and immunisation series for Chad."""
        return await collect_unicef("health", self.source_errors)

    async def _collect_dhs(self) -> list[dict[str, Any]]:
        """DHS Program survey indicators for Chad: national and by region (surveys 1997, 2004, 2014)."""
        records: list[dict[str, Any]] = []
        ids = ",".join(DHS_INDICATORS)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for breakdown in ("national", "subnational"):
                page, pages = 1, 1
                while page <= min(pages, MAX_PAGES):
                    reason: list[str] = []
                    payload = await self.fetch_json_with_retry(
                        client, DHS_URL, params={"countryIds": "TD", "indicatorIds": ids, "breakdown": breakdown,
                                                "perpage": PAGE, "page": page, "f": "json"},
                        throttle_seconds=0.3, errors=reason)
                    if payload is None:
                        self.source_errors.append(f"DHS {breakdown} page {page}: {reason[0] if reason else 'no answer'}")
                        break
                    records.extend(parse_dhs(payload))
                    pages = int(payload.get("TotalPages", 1) or 1) if isinstance(payload, dict) else 1
                    page += 1
        if not records:
            raise RuntimeError("DHS Program returned nothing")
        return records

    async def _collect_open_street_map(self) -> list[dict[str, Any]]:
        """Mapped hospitals and clinics, pharmacies and water points per region (OpenStreetMap contributors)."""
        return await collect_osm_counts([HOSPITALS, PHARMACIES, WATER_POINTS], self.source_errors)

    def _get_demo_records(self) -> list[dict[str, Any]]:
        return [
            {
                "year": 2023,
                "value": 53.0,
                "source": "World Bank",
                "indicator": "Life expectancy at birth",
                "unit": "years",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 105.9,
                "source": "World Bank",
                "indicator": "Under-5 mortality rate",
                "unit": "per 1,000 live births",
                "region": "national",
            },
            {
                "year": 2023,
                "value": 748.0,
                "source": "World Bank",
                "indicator": "Maternal mortality ratio",
                "unit": "per 100,000 live births",
                "region": "national",
            },
        ]

    async def _collect_world_bank(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for code, (name, unit) in self.WORLD_BANK_INDICATORS.items():
                url = f"https://api.worldbank.org/v2/country/{self.CHAD_ISO3}/indicator/{code}"
                params = {"format": "json", "per_page": 100, "date": wb_years(2000)}
                payload = await self.fetch_json_with_retry(client, url, params=params, throttle_seconds=0.15)
                if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
                    for item in payload[1]:
                        if not isinstance(item, dict):
                            continue
                        val = item.get("value")
                        date_str = str(item.get("date", "")).strip()
                        if val is not None and date_str.isdigit():
                            try:
                                records.append(
                                    {
                                        "year": int(date_str),
                                        "value": round(float(val), 2),
                                        "source": "World Bank",
                                        "indicator": name,
                                        "unit": unit,
                                        "region": "national",
                                        "url": url,
                                    }
                                )
                            except (ValueError, TypeError):
                                continue
        return records

    def normalize(self, record: dict[str, Any]) -> ObservationCreate | None:
        if record.get("value") is None or not record.get("year"):
            return None

        yr = int(record["year"])
        mo = int(record.get("month", 1))
        dy = int(record.get("day", 1))
        ref_date = date(yr, mo, dy)
        unit_str = str(record.get("unit", "unit"))[:40]

        val = float(record["value"])
        if not val.is_integer():
            val = round(val, 2)

        licence, notes = source_terms(str(record["source"]), "HealthAgent")
        return ObservationCreate(
            sector="health",
            indicator=str(record["indicator"]),
            value=val,
            unit=unit_str,
            reference_date=ref_date,
            region=str(record.get("region", "national")),
            source=str(record["source"])[:30],
            source_url=record.get("url"),
            license=licence,
            notes=notes,
        )
