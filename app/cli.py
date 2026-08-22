import argparse
import asyncio
from pathlib import Path

from app.agents import AgricultureAgent
from app.services.export import observations_to_csv, observations_to_json
from app.services.storage import ObservationRepository


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

    args = parser.parse_args()
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
        target = Path("data/exports") / f"{args.sector or 'all'}-observations.{ext}"
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
