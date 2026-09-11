import csv
import json
from io import StringIO
from typing import Any

# Characters that spreadsheet apps (Excel, Google Sheets, LibreOffice) treat as
# the start of a formula when a cell value begins with them. A malicious or
# compromised external data source (indicator/source/notes text) could smuggle
# a formula (e.g. "=HYPERLINK(...)") into the CSV, which executes when a
# researcher opens the export - this is CWE-1236 (CSV/Formula Injection).
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


def _escape_csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def observations_to_csv(rows: list[dict]) -> str:
    output = StringIO()
    fieldnames = ["id", "sector", "indicator", "value", "unit", "reference_date", "country_code", "region", "source", "source_url", "license", "notes", "collected_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _escape_csv_cell(val) for key, val in row.items()})
    return output.getvalue()


def observations_to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)

