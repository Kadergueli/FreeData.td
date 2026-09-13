import csv
import json
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

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
    fieldnames = [
        "id",
        "sector",
        "indicator",
        "value",
        "unit",
        "reference_date",
        "country_code",
        "region",
        "source",
        "source_url",
        "license",
        "notes",
        "collected_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _escape_csv_cell(val) for key, val in row.items()})
    return output.getvalue()


def observations_to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)


def observations_to_xml(rows: list[dict]) -> str:
    root = ET.Element("freedatatd_export", count=str(len(rows)))
    for row in rows:
        obs_elem = ET.SubElement(root, "observation")
        for k, v in row.items():
            child = ET.SubElement(obs_elem, str(k))
            child.text = str(v) if v is not None else ""
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def observations_to_parquet(rows: list[dict]) -> bytes:
    if not rows:
        schema = pa.schema([
            ("id", pa.string()),
            ("sector", pa.string()),
            ("indicator", pa.string()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("reference_date", pa.string()),
            ("country_code", pa.string()),
            ("region", pa.string()),
            ("source", pa.string()),
            ("source_url", pa.string()),
            ("license", pa.string()),
            ("notes", pa.string()),
            ("collected_at", pa.string()),
        ])
        table = pa.Table.from_batches([], schema=schema)
    else:
        keys = list(rows[0].keys())
        data_dict = {}
        for k in keys:
            col_vals = []
            for r in rows:
                v = r.get(k)
                if v is not None and not isinstance(v, (int, float, str, bool)):
                    col_vals.append(str(v))
                else:
                    col_vals.append(v)
            data_dict[k] = col_vals
        table = pa.Table.from_pydict(data_dict)

    out = BytesIO()
    pq.write_table(table, out)
    return out.getvalue()
