"""Copernicus ERA5-Land (CDS): hourly point series turned into monthly values for one region.

Dataset "reanalysis-era5-land-timeseries", CSV, one file per variable inside a zip:
  t2m  = 2 m temperature, kelvin, hourly
  tp   = total precipitation, metres. Either ACCUMULATED from 00 UTC of each day (then the daily
         total is the largest value of the span, stamped 00:00 of day D+1) or hourly amounts (then
         it is their sum). The first real download (Moundou) showed the largest-value rule giving
         about a fifth of the rain, so the mode is detected in the data: a value that falls inside
         a day (hour 1..23) can only be an hourly amount.
Only complete months are returned: a half month would give a misleading mean."""
from __future__ import annotations

import calendar
import csv
import io
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

DATASET = "reanalysis-era5-land-timeseries"
CDS_URL = "https://cds.climate.copernicus.eu/api"
MAX_DAYS_PER_REQUEST = 366          # one year per request is what the CDS accepted in tests
SOURCE = "Copernicus ERA5-Land"

INDICATORS = {
    "mean": ("Monthly mean temperature", "°C"),
    "max": ("Monthly max temperature", "°C"),
    "min": ("Monthly min temperature", "°C"),
    "precip": ("Monthly precipitation", "mm/day"),
}


def chunks(start: date, end: date, max_days: int = MAX_DAYS_PER_REQUEST) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def build_request(lat: float, lon: float, start: date, end: date) -> dict[str, Any]:
    return {
        "variable": ["2m_temperature", "total_precipitation"],
        "location": {"longitude": lon, "latitude": lat},
        "date": [f"{start.isoformat()}/{end.isoformat()}"],
        "data_format": "csv",
    }


def read_zip(blob: bytes) -> dict[str, list[tuple[datetime, float]]]:
    """{'t2m': [(time, kelvin)...], 'tp': [(time, metres)...]} from the downloaded zip."""
    series: dict[str, list[tuple[datetime, float]]] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            for row in csv.DictReader(io.StringIO(z.read(name).decode("utf-8", "replace"))):
                for var in ("t2m", "tp"):
                    if var in row and row[var] not in ("", None):
                        series.setdefault(var, []).append(
                            (datetime.fromisoformat(row["valid_time"]), float(row[var])))
    return series


def precip_is_hourly(tp: list[tuple[datetime, float]]) -> bool:
    """True when the values are hourly amounts: an accumulation never falls from one hour to the next
    inside a day (it restarts after the 00:00 value)."""
    for (t0, v0), (t1, v1) in zip(tp, tp[1:]):
        if t0.hour != 0 and t1.hour != 0 and t1 - t0 == timedelta(hours=1) and v1 < v0 - 1e-9:
            return True
    return False


def monthly(series: dict[str, list[tuple[datetime, float]]]) -> list[dict[str, Any]]:
    """[{year, month, kind, value}] for each complete month, kind in mean|max|min|precip."""
    temps: dict[date, list[float]] = defaultdict(list)
    for t, kelvin in series.get("t2m", []):
        temps[t.date()].append(kelvin - 273.15)
    accum: dict[date, list[float]] = defaultdict(list)
    tp = sorted(series.get("tp", []))
    hourly = precip_is_hourly(tp)
    for t, metres in tp:
        # 00:00 belongs to the day that just ended; hours 01..23 to the current day
        accum[t.date() - timedelta(days=1) if t.hour == 0 else t.date()].append(metres * 1000.0)

    by_month: dict[tuple[int, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for day, vals in temps.items():
        if len(vals) < 24:
            continue                    # incomplete day
        m = by_month[(day.year, day.month)]
        m["mean"].append(sum(vals) / len(vals))
        m["max"].append(max(vals))
        m["min"].append(min(vals))
    for day, vals in accum.items():
        if (day.year, day.month) in by_month and day in temps and len(temps[day]) >= 24:
            by_month[(day.year, day.month)]["precip"].append(sum(vals) if hourly else max(vals))

    out = []
    for (year, month), kinds in sorted(by_month.items()):
        days = calendar.monthrange(year, month)[1]
        if len(kinds["mean"]) < days:
            continue                    # the month is not complete
        for kind, values in kinds.items():
            if kind == "precip" and len(values) < days:
                continue
            out.append({"year": year, "month": month, "kind": kind, "value": sum(values) / len(values)})
    return out


def fetch_region_blob(url: str, key: str, lat: float, lon: float, start: date, end: date) -> bytes:
    """Blocking call (cdsapi waits for the CDS queue): run it in a worker thread."""
    import tempfile
    from pathlib import Path

    import cdsapi

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "era5.zip"
        cdsapi.Client(url=url, key=key, quiet=True, progress=False).retrieve(
            DATASET, build_request(lat, lon, start, end), str(target))
        return target.read_bytes()
