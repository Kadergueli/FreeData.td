import csv
import json
import xml.etree.ElementTree as ET
from io import BytesIO, StringIO
from typing import Any

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    # A missing/failed pyarrow install must never take down the WHOLE app -
    # it's a real dependency (in requirements.txt) for one export format, not
    # a core requirement. Every other route keeps working; only
    # observations_to_parquet() below reports a clear, contained error.
    pa = None
    pq = None
    _PYARROW_AVAILABLE = False

# Characters that spreadsheet apps (Excel, Google Sheets, LibreOffice) treat as
# the start of a formula when a cell value begins with them. A malicious or
# compromised external data source (indicator/source/notes text) could smuggle
# a formula (e.g. "=HYPERLINK(...)") into the CSV, which executes when a
# researcher opens the export - this is CWE-1236 (CSV/Formula Injection).
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@")


# Fixed, deterministic field order shared by CSV/XML/Parquet exports. Using
# one shared list (not each row's own keys) keeps every export format
# structurally consistent regardless of what any individual row happens to
# contain - e.g. previously, XML iterated `row.items()` directly and Parquet
# inferred its schema from `rows[0].keys()`, so the exact set/order of
# columns could silently vary between calls depending on what keys happened
# to be present in the data at that moment.
_EXPORT_FIELDS = [
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


def _escape_csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def observations_to_csv(rows: list[dict]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
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
        for key in _EXPORT_FIELDS:
            child = ET.SubElement(obs_elem, key)
            value = row.get(key)
            child.text = str(value) if value is not None else ""
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def observations_to_parquet(rows: list[dict]) -> bytes:
    if not _PYARROW_AVAILABLE:
        raise RuntimeError(
            "Parquet export is temporarily unavailable on this server "
            "(the pyarrow dependency is not installed). Try CSV or JSON instead."
        )

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

    data_dict: dict[str, list[Any]] = {}
    for key in _EXPORT_FIELDS:
        values = []
        for row in rows:
            value = row.get(key)
            if value is None:
                values.append(None)
            elif key == "value":
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    # Should not happen (ObservationCreate.value is validated
                    # as a finite float at write time), but never let one
                    # malformed legacy row crash the whole export.
                    values.append(None)
            else:
                values.append(str(value))
        data_dict[key] = values

    table = pa.Table.from_pydict(data_dict, schema=schema)

    out = BytesIO()
    pq.write_table(table, out)
    return out.getvalue()
