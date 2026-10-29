import argparse
import asyncio
from pathlib import Path

from app.agents import AgricultureAgent
from app.services.export import observations_to_csv, observations_to_json
from app.services.storage import ObservationRepository


async def probe_prices() -> str:
    """One real request to the FEWS NET API, summarised: does it answer, what shape, how fresh."""
    import httpx

    from app.agents.fews_prices import FEWS_URL, extract_items, parse_record, resolve_collisions

    from datetime import UTC, datetime

    # same window as the real collector (MarketsAgent.FEWS_HISTORY_YEARS), so the probe tells the truth
    params = {"country_code": "TD", "format": "json", "start_date": f"{datetime.now(UTC).year - 2}-01-01"}
    lines = [f"GET {FEWS_URL} {params}"]
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(FEWS_URL, params=params, headers={"User-Agent": "FreeData.td probe"})
    except httpx.HTTPError as exc:
        return "\n".join(lines + [f"NETWORK ERROR: {exc}"])
    size = len(getattr(response, "content", b"") or b"") / 1e6
    elapsed = getattr(response, "elapsed", None)
    took = f" in {elapsed.total_seconds():.0f}s" if elapsed else ""
    lines.append(f"HTTP {response.status_code}, content-type: {response.headers.get('content-type')}, {size:.1f} MB{took}")
    if response.status_code != 200:
        return "\n".join(lines + [f"BODY (start): {response.text[:300]!r}"])
    try:
        items, next_url = extract_items(response.json())
    except ValueError as exc:
        return "\n".join(lines + [f"UNREADABLE: {exc}", f"BODY (start): {response.text[:300]!r}"])
    lines.append(f"records on first page: {len(items)}; next page: {'yes' if next_url else 'no'}")
    if not items:
        return "\n".join(lines + ["EMPTY: the API answered but returned no price for Chad."])
    lines.append(f"fields of the first record: {sorted(items[0].keys())}")
    parsed = [p for p in (parse_record(i) for i in items) if p]
    lines.append(f"usable price records: {len(parsed)} of {len(items)}")
    parsed, renamed, dropped = resolve_collisions(parsed)
    lines.append(f"same product/market/date listed twice: {renamed} told apart by unit, {dropped} duplicate(s) dropped -> {len(parsed)} to store")
    if parsed:
        newest = max((p["year"], p["month"], p["day"]) for p in parsed)
        lines.append(f"newest price date: {newest[0]}-{newest[1]:02d}-{newest[2]:02d}")
        lines.append(f"markets/regions: {sorted({p['region'] for p in parsed})[:15]}")
        lines.append(f"products: {sorted({p['indicator'].split(' price')[0] for p in parsed})[:15]}")
        lines.append(f"example: {parsed[0]['indicator']} = {parsed[0]['value']} {parsed[0]['unit']} ({parsed[0]['region']})")
    else:
        lines.append("NONE USABLE: the field names probably differ; send this output to Claude.")
    return "\n".join(lines)


async def probe_sources() -> str:
    """Real requests to the IMF, the WFP file on HDX and OpenStreetMap (one region), through the
    same code the collectors use. No database needed."""
    from types import SimpleNamespace

    import httpx

    from app.agents import osm
    from app.agents.economy import EconomyAgent
    from app.agents.markets import MarketsAgent

    lines: list[str] = []

    econ = EconomyAgent(SimpleNamespace())
    try:
        rows = await econ._collect_imf()
        years = sorted({r["year"] for r in rows})
        lines.append(f"IMF: OK, {len(rows)} values, {len({r['indicator'] for r in rows})} series, years {years[0]}-{years[-1]}")
        lines.append(f"     example: {rows[0]['indicator']} {rows[0]['year']} = {rows[0]['value']} {rows[0]['unit']}")
    except Exception as exc:
        lines.append(f"IMF: FAILED - {exc}")
    lines += [f"     note: {e}" for e in econ.source_errors]

    markets = MarketsAgent(SimpleNamespace())
    try:
        rows = await markets._collect_wfp_prices()
        lines.append(f"WFP (HDX): OK, {len(rows)} prices, {len({r['region'] for r in rows})} markets, "
                     f"{len({r['indicator'] for r in rows})} products, newest {max((r['year'], r['month']) for r in rows)}")
        lines.append(f"     example: {rows[0]['indicator']} = {rows[0]['value']} {rows[0]['unit']} ({rows[0]['region']})")
    except Exception as exc:
        lines.append(f"WFP (HDX): FAILED - {exc}")

    import time

    from app.agents.transport import TransportAgent

    transport = TransportAgent(SimpleNamespace())
    try:
        rows = await transport._collect_airports()
        national = next((r for r in rows if r["region"] == "national"), None)
        lines.append(f"OurAirports: OK, {len(rows)} values, {len({r['region'] for r in rows}) - 1} regions"
                     + (f", {int(national['value'])} airports and airstrips in Chad" if national else ""))
    except Exception as exc:
        lines.append(f"OurAirports: FAILED - {exc}")

    # Schools and hospitals are collected per region; the national roads/aerodromes queries are only
    # probed to see whether the public Overpass servers can answer them (they could not, twice).
    for feature in (osm.SCHOOLS, osm.HOSPITALS):
        began = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(osm.REQUEST_TIMEOUT, connect=15.0)) as client:
                payload, reason = await osm._query(client, osm.build_query("TD" if feature.national else "TD-LC", feature))
            counts = osm.parse_counts(payload, 1) if payload is not None else None
            took = f"{time.monotonic() - began:.0f}s"
            if counts is None:
                lines.append(f"OpenStreetMap ({'whole country' if feature.national else 'Lac'}, {feature.unit}): FAILED after {took} - "
                             f"{reason or 'unexpected answer: ' + str(payload)[:200]}")
            else:
                note = "  <- zero: the ISO area was probably not found" if counts[0] == 0 else ""
                lines.append(f"OpenStreetMap ({'whole country' if feature.national else 'Lac'}, {feature.unit}): OK in {took}, {counts[0]}{note}")
        except Exception as exc:
            lines.append(f"OpenStreetMap ({'whole country' if feature.national else 'Lac'}, {feature.unit}): FAILED - {exc}")
    return "\n".join(lines)


INSEED_BASE = "https://chad.opendataforafrica.org/api/1.0/sdmx/data"
# (label, dataflow, key) taken from the INSEED "Principaux indicateurs statistiques" page.
_PROVINCE_KEYS = ("TD+TD-BA+TD-BO+TD-CB+TD-GR+TD-HL+TD-KA+TD-LC+TD-LO+TD-LR+TD-MA+TD-MO+TD-ME+TD-MC+TD-OD+TD-SA"
                  "+TD-TA+TD-WF+TD-ND+TD-BG+TD-EO+TD-SI+TD-TI+TD-EE")
# Datasets already imported by InseedAgent use their registered key; the others are samples to look at
# (keys exactly as written on the INSEED page) before they get a parser.
INSEED_PROBES = [
    ("Indice des prix a la consommation", "xxhsxif", None),
    ("Etablissements de sante par province", "urtpzwb", None),
    ("Population par age et sexe", "pqvhyxg",
     "POPT+P0_4+P5_9+P10_14+P15_19+P20_24+P25_29+P30_34+P35_39+P40_44+P45_49+P50_54+P55_59+P60_64+P65_69+P70_74+P75_79+P80_P.M+F.U+R"),
    ("Scolarisation par province", "gkvamx", f"TBS.T+G+F.{_PROVINCE_KEYS}"),
]
INSEED_PAUSE_SECONDS = 4


async def probe_inseed(save_dir: Path | None = None) -> str:
    """A few real requests to the INSEED open-data portal (SDMX API) with the honest
    FreeData.td user agent. For each: status, content type, size, and the start of the data
    section. Successful answers are saved as files (default data/raw/) so they can be sent
    to Claude. A Cloudflare bot challenge is reported as such; it is never worked around."""
    import httpx

    save_dir = save_dir or Path("data/raw")
    lines = [f"INSEED SDMX API: {INSEED_BASE}"]
    headers = {"User-Agent": "FreeData.td probe (open data platform for Chad)"}
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            from app.agents.inseed import DATASETS

            for i, (label, flow, key) in enumerate(INSEED_PROBES):
                key = key or DATASETS[flow].key
                if i:
                    await asyncio.sleep(INSEED_PAUSE_SECONDS)
                # the key is built into the URL as written on the INSEED page: '+' means "or" in SDMX
                url = f"{INSEED_BASE}/{flow}?key={key}"
                lines.append(f"\n== {label} ({flow}) ==")
                try:
                    r = await client.get(url, headers=headers)
                except httpx.HTTPError as exc:
                    lines.append(f"NETWORK ERROR: {type(exc).__name__}: {exc}")
                    continue
                body = getattr(r, "text", "") or ""
                size = len(getattr(r, "content", b"") or b"") / 1e3
                lines.append(f"HTTP {r.status_code}, {r.headers.get('content-type')}, {size:.1f} kB, server: {r.headers.get('server')}")
                if r.status_code == 403 and "Just a moment" in body:
                    lines.append("   BLOCKED by a Cloudflare bot challenge (not an INSEED error).")
                    continue
                if r.status_code != 200:
                    lines.append("   " + " ".join(body[:300].split()))
                    continue
                start = max(body.find("<DataSet"), body.find('"dataSets"'), 0)
                lines.append("   " + " ".join(body[start:start + 700].split()))
                try:
                    save_dir.mkdir(parents=True, exist_ok=True)
                    target = save_dir / f"inseed_{flow}.xml"
                    target.write_text(body, encoding="utf-8")
                    lines.append(f"   saved: {target}")
                except OSError as exc:
                    lines.append(f"   could not save the answer: {exc}")
    except Exception as exc:  # never crash a diagnostic: show what happened
        lines.append(f"ERROR: {type(exc).__name__}: {exc}")
    return "\n".join(lines)


async def import_inseed(paths: list[Path], repository=None) -> str:
    """Turn saved INSEED SDMX files into observations through the normal pipeline."""
    from app.agents.inseed import InseedAgent, load_files

    if not paths:
        return "No file to import: run probe-inseed first (it saves data/raw/inseed_*.xml)."
    by_sector, problems = load_files(paths)
    repository = repository or ObservationRepository()
    lines = []
    for sector, records in by_sector.items():
        result = await InseedAgent(repository, sector, records).run("files")
        lines.append(f"{sector}: {len(records)} read, {result.accepted} accepted, {result.rejected} rejected, {result.stored} stored")
    lines += [f"PROBLEM {p}" for p in problems]
    return "\n".join(lines) or "Nothing imported."


def main() -> None:
    parser = argparse.ArgumentParser(description="FreeDatatd command-line tools")
    commands = parser.add_subparsers(dest="command", required=True)

    agriculture = commands.add_parser("collect-agriculture", help="Run AgricultureAgent")
    agriculture.add_argument(
        "--source",
        choices=["all", "world-bank", "open-meteo", "wfp-markets", "demo"],
        default="all",
        help="Data source to collect from",
    )
    agriculture.add_argument("--demo", action="store_true", help="Use deterministic sample data")

    export = commands.add_parser("export", help="Create a data export (CSV or JSON)")
    export.add_argument("--sector", default=None, help="Sector filter (e.g. agriculture)")
    export.add_argument("--format", choices=["csv", "json"], default="csv", help="Export format")

    imp = commands.add_parser(
        "import-inseed",
        help="Import the INSEED answers saved by probe-inseed (data/raw/inseed_*.xml) into the database",
    )
    imp.add_argument("files", nargs="*", help="Files to import (default: every data/raw/inseed_*.xml)")
    commands.add_parser(
        "probe-inseed",
        help="Check the INSEED open-data (SDMX) API from this machine and show the response format",
    )
    commands.add_parser(
        "probe-sources",
        help="Check the IMF, WFP (HDX) and OpenStreetMap collectors from this machine (no database needed)",
    )
    commands.add_parser(
        "probe-prices",
        help="Check the FEWS NET market-price API for Chad from this machine (no database needed)",
    )

    args = parser.parse_args()

    if args.command == "import-inseed":
        print(asyncio.run(import_inseed([Path(f) for f in args.files] or sorted(Path("data/raw").glob("inseed_*.xml")))))
        return
    if args.command == "probe-inseed":
        print(asyncio.run(probe_inseed()))
        return
    if args.command == "probe-sources":
        print(asyncio.run(probe_sources()))
        return
    if args.command == "probe-prices":
        print(asyncio.run(probe_prices()))
        return

    repository = ObservationRepository()

    if args.command == "collect-agriculture":
        source = "demo" if args.demo else args.source
        print(f"Starting AgricultureAgent harvest from source: {source}...")
        result = asyncio.run(AgricultureAgent(repository).run(source))
        print(result.model_dump_json(indent=2))
        return

    if args.command == "export":
        rows = repository.list_observations(sector=args.sector, limit=5000)
        ext = args.format
        # Sanitize before using in a filesystem path: --sector is free text, and
        # without this a value like '../../.env' could write outside data/exports/.
        safe_sector = "".join(c for c in (args.sector or "all") if c.isalnum() or c in "-_") or "all"
        target = Path("data/exports") / f"{safe_sector}-observations.{ext}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if ext == "json":
            content = observations_to_json(rows)
            target.write_text(content, encoding="utf-8")
        else:
            content = observations_to_csv(rows)
            target.write_text(content, encoding="utf-8", newline="")
        print(f"Exported {len(rows)} observations to {target}")


if __name__ == "__main__":
    main()
