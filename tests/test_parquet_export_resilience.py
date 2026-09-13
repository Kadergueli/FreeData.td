"""Regression tests for the production outage: main.py imported
observations_to_parquet at module level from `import pyarrow as pa`, which
was never added to requirements.txt. On Render this crashed the ENTIRE app
at startup with ModuleNotFoundError - not just the parquet export feature,
the whole site was down (uvicorn couldn't even load app.main).

pyarrow is now a real dependency in requirements.txt, but the import in
export.py is also defensive as a second line of defense: even if pyarrow is
ever missing/fails to build in some future environment again, the rest of
the app must keep working, with only /api/v1/export/parquet reporting a
clean, contained 503 instead of the whole process refusing to start.

Also covers the merged fix for a second issue found in an alternate patch
someone else proposed for the same outage: XML/Parquet exports now use one
shared, deterministic field list (_EXPORT_FIELDS) instead of each row's own
keys - a Python set (used in that alternate patch) doesn't guarantee stable
iteration order across process restarts, so a plain list is used instead.
"""

import subprocess
import sys

import pytest


def test_app_imports_successfully_even_without_pyarrow():
    """Simulates pyarrow being completely unavailable (as if the package
    failed to install) and verifies the app module still imports cleanly -
    this is the actual scenario that took production down. Runs in a fresh
    subprocess so the simulated missing import can never leak into (or be
    contaminated by) any other test in this suite."""
    script = (
        "import builtins, sys\n"
        "real_import = builtins.__import__\n"
        "def fake_import(name, *a, **kw):\n"
        "    if name == 'pyarrow' or name.startswith('pyarrow.'):\n"
        "        raise ModuleNotFoundError(f\"No module named '{name}'\")\n"
        "    return real_import(name, *a, **kw)\n"
        "builtins.__import__ = fake_import\n"
        "import app.main\n"
        "import app.services.export as export_module\n"
        "assert export_module._PYARROW_AVAILABLE is False\n"
        "print('OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "OK" in result.stdout


def test_parquet_export_raises_clean_runtime_error_without_pyarrow(monkeypatch):
    import app.services.export as export_module

    monkeypatch.setattr(export_module, "_PYARROW_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="pyarrow"):
        export_module.observations_to_parquet([])


def test_parquet_endpoint_returns_503_not_500_when_pyarrow_unavailable(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main_module

    monkeypatch.setattr(
        main_module, "observations_to_parquet",
        lambda rows: (_ for _ in ()).throw(RuntimeError("Parquet export is temporarily unavailable")),
    )

    client = TestClient(main_module.app)
    response = client.get("/api/v1/export/parquet")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


from app.services.export import _PYARROW_AVAILABLE

_requires_pyarrow = pytest.mark.skipif(
    not _PYARROW_AVAILABLE,
    reason="pyarrow is not installed in this environment (e.g. no cp314 wheel available yet)",
)


@_requires_pyarrow
def test_parquet_export_actually_works_when_pyarrow_is_available():
    from app.services.export import observations_to_parquet

    content = observations_to_parquet([
        {"id": 1, "sector": "health", "indicator": "Test", "value": 1.0, "unit": "u",
         "reference_date": "2024-01-01", "country_code": "TCD", "region": "national",
         "source": "Test", "source_url": None, "license": "CC BY 4.0", "notes": None,
         "collected_at": "2024-01-01T00:00:00Z"},
    ])
    assert isinstance(content, bytes)
    assert len(content) > 0


@_requires_pyarrow
def test_parquet_handles_a_malformed_value_without_crashing():
    """value should always be a clean float by the time it reaches export
    (ObservationCreate validates this at write time), but the export layer
    must never crash the whole download over one bad legacy row either."""
    from app.services.export import observations_to_parquet

    content = observations_to_parquet([
        {"id": 1, "sector": "health", "indicator": "Test", "value": "not-a-number",
         "unit": "u", "reference_date": "2024-01-01", "country_code": "TCD",
         "region": "national", "source": "Test", "source_url": None,
         "license": "CC BY 4.0", "notes": None, "collected_at": "2024-01-01T00:00:00Z"},
    ])
    assert isinstance(content, bytes)
    assert len(content) > 0


def test_xml_export_still_works_and_needs_no_pyarrow():
    from app.services.export import observations_to_xml

    xml_text = observations_to_xml([
        {"id": 1, "sector": "health", "indicator": "Test <script>", "value": 1.0},
    ])
    assert "<observation>" in xml_text
    # ElementTree must auto-escape XML-special characters in text content.
    assert "<script>" not in xml_text
    assert "&lt;script&gt;" in xml_text


def test_xml_export_uses_fixed_deterministic_field_order():
    """Regression test for the alternate patch's use of a Python set for
    allowed fields, which doesn't guarantee stable iteration order across
    process restarts. Runs the export twice with rows in a different key
    order and checks the resulting XML element order is identical both
    times within this run, and matches the documented _EXPORT_FIELDS order."""
    from app.services.export import _EXPORT_FIELDS, observations_to_xml

    row_a = {"id": 1, "sector": "health", "value": 1.0}
    row_b = {"value": 1.0, "sector": "health", "id": 1}  # same data, different key order

    xml_a = observations_to_xml([row_a])
    xml_b = observations_to_xml([row_b])
    assert xml_a == xml_b

    # The element order within one <observation> must follow _EXPORT_FIELDS.
    # ElementTree self-closes empty-text elements (e.g. "<indicator />"), so
    # search for the opening-tag prefix without requiring a trailing ">".
    first_three_expected = _EXPORT_FIELDS[:3]
    positions = [xml_a.index(f"<{field}") for field in first_three_expected]
    assert positions == sorted(positions)


def test_csv_export_uses_fixed_field_order_regardless_of_row_key_order():
    from app.services.export import _EXPORT_FIELDS, observations_to_csv

    csv_text = observations_to_csv([{"value": 1.0, "sector": "health", "id": 1}])
    header_line = csv_text.splitlines()[0]
    assert header_line == ",".join(_EXPORT_FIELDS)
