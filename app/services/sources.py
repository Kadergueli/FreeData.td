"""The sources each sector can be collected from, one at a time (admin area) or all together.

`agent.collect("<id>")` accepts exactly these ids (plus "all" and "demo"): a test compares this table
with the "Supported:" list of every agent, so a new source cannot be added to an agent and forgotten here."""
from __future__ import annotations

SOURCE_LABELS: dict[str, str] = {
    "world-bank": "World Bank", "imf": "IMF", "open-meteo": "Open-Meteo", "nasa-power": "NASA POWER",
    "nasa-power-agro": "NASA POWER (agro)", "nasa-firms": "NASA FIRMS", "unhcr": "UNHCR",
    "unesco-uis": "UNESCO UIS", "unicef": "UNICEF", "open-street-map": "OpenStreetMap",
    "who-gho": "WHO GHO", "dhs": "DHS Program", "fews-net": "FEWS NET", "wfp": "WFP prices",
    "faostat": "FAOSTAT", "ourairports": "OurAirports", "open-meteo-transport": "Open-Meteo (transport)",
    "pink-sheet": "World Bank Pink Sheet", "copernicus-era5": "Copernicus ERA5-Land",
}

SECTOR_SOURCES: dict[str, tuple[str, ...]] = {
    "agriculture": ("world-bank", "open-meteo", "nasa-power-agro"),
    "environment": ("open-meteo", "nasa-power", "nasa-firms", "copernicus-era5"),
    "markets": ("world-bank", "fews-net", "wfp", "faostat"),
    "economy": ("world-bank", "imf"),
    "health": ("world-bank", "who-gho", "dhs", "unicef", "open-street-map"),
    "energy": ("world-bank", "nasa-power"),
    "transport": ("world-bank", "ourairports", "open-street-map", "open-meteo-transport"),
    "education": ("world-bank", "unesco-uis", "unicef", "open-street-map"),
    "demography": ("world-bank", "unhcr"),
    "telecom": ("world-bank",),
    "trade": ("world-bank", "pink-sheet"),
}


def source_catalogue() -> dict[str, list[dict[str, str]]]:
    """{sector: [{"id": "who-gho", "label": "WHO GHO"}, ...]} for the admin screen."""
    return {sec: [{"id": s, "label": SOURCE_LABELS.get(s, s)} for s in ids] for sec, ids in SECTOR_SOURCES.items()}


def validate_sources(sources: dict[str, list[str]] | None) -> None:
    """ValueError naming what is wrong: an unknown sector, or a source that sector does not have."""
    for sector, ids in (sources or {}).items():
        if sector not in SECTOR_SOURCES:
            raise ValueError(f"unknown sector: {sector}")
        bad = [s for s in ids if s not in SECTOR_SOURCES[sector]]
        if bad:
            raise ValueError(f"unknown source(s) for {sector}: {', '.join(bad)}")
        if not ids:
            raise ValueError(f"no source given for {sector}")
