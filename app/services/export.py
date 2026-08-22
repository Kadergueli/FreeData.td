import csv
import json
from io import StringIO


def observations_to_csv(rows: list[dict]) -> str:
    output = StringIO()
    fieldnames = ["id", "sector", "indicator", "value", "unit", "reference_date", "country_code", "region", "source", "source_url", "license", "notes", "collected_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def observations_to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)

