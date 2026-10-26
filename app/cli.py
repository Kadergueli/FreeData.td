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

    params = {"country_code": "TD", "format": "json", "start_date": "2024-01-01"}
    lines = [f"GET {FEWS_URL} {params}"]
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(FEWS_URL, params=params, headers={"User-Agent": "FreeData.td probe"})
    except httpx.HTTPError as exc:
        return "\n".join(lines + [f"NETWORK ERROR: {exc}"])
    lines.append(f"HTTP {response.status_code}, content-type: {response.headers.get('content-type')}")
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

    commands.add_parser(
        "probe-prices",
        help="Check the FEWS NET market-price API for Chad from this machine (no database needed)",
    )

    args = parser.parse_args()

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
