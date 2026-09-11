"""Regression tests for the file-by-file security/data-integrity pass:
- ObservationCreate rejects NaN/Infinity and neutralizes non-http(s) source_url.
- CSV export escapes formula-injection-triggering cell values (CWE-1236).
- The Supabase retry helper actually retries transient failures before
  giving up, instead of failing on the very first blip.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import ObservationCreate
from app.services.export import observations_to_csv
from app.services.storage import _with_retry


def _make(**overrides):
    base = dict(
        sector="health",
        indicator="Test indicator",
        value=1.0,
        unit="units",
        reference_date=date(2024, 1, 1),
        source="World Bank",
    )
    base.update(overrides)
    return ObservationCreate(**base)


def test_nan_value_is_rejected():
    with pytest.raises(ValidationError):
        _make(value=float("nan"))


def test_infinity_value_is_rejected():
    with pytest.raises(ValidationError):
        _make(value=float("inf"))
    with pytest.raises(ValidationError):
        _make(value=float("-inf"))


def test_finite_value_is_accepted():
    obs = _make(value=53.5)
    assert obs.value == 53.5


def test_javascript_uri_source_url_is_neutralized():
    obs = _make(source_url="javascript:alert(1)")
    assert obs.source_url is None


def test_http_source_url_is_kept():
    obs = _make(source_url="https://api.worldbank.org/v2/country/TCD")
    assert obs.source_url == "https://api.worldbank.org/v2/country/TCD"


def test_csv_export_escapes_formula_trigger_chars():
    rows = [
        {
            "id": 1,
            "sector": "health",
            "indicator": "=HYPERLINK(\"http://evil.example\",\"click me\")",
            "value": 1.0,
            "unit": "u",
            "reference_date": "2024-01-01",
            "country_code": "TCD",
            "region": "national",
            "source": "@SUM(1+1)",
            "source_url": None,
            "license": "CC BY 4.0",
            "notes": "+cmd|'/c calc'!A1",
            "collected_at": "2024-01-01T00:00:00Z",
        }
    ]
    csv_text = observations_to_csv(rows)
    assert '="HYPERLINK' not in csv_text  # never left bare/unescaped after the = sign in the raw cell
    assert "'=HYPERLINK" in csv_text
    assert "'@SUM" in csv_text
    assert "'+cmd" in csv_text


def test_csv_export_leaves_normal_values_untouched():
    rows = [
        {
            "id": 1, "sector": "health", "indicator": "Life expectancy",
            "value": 53.0, "unit": "years", "reference_date": "2024-01-01",
            "country_code": "TCD", "region": "national", "source": "World Bank",
            "source_url": None, "license": "CC BY 4.0", "notes": None,
            "collected_at": "2024-01-01T00:00:00Z",
        }
    ]
    csv_text = observations_to_csv(rows)
    assert "Life expectancy" in csv_text
    assert "'Life expectancy" not in csv_text


def test_with_retry_succeeds_on_first_try():
    calls = []

    def op():
        calls.append(1)
        return "ok"

    assert _with_retry(op, attempts=3, base_delay=0) == "ok"
    assert len(calls) == 1


def test_with_retry_retries_then_succeeds():
    calls = []

    def op():
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("simulated transient failure")
        return "ok"

    assert _with_retry(op, attempts=3, base_delay=0) == "ok"
    assert len(calls) == 2


def test_with_retry_raises_after_exhausting_attempts():
    calls = []

    def op():
        calls.append(1)
        raise ConnectionError("persistent failure")

    with pytest.raises(ConnectionError):
        _with_retry(op, attempts=3, base_delay=0)
    assert len(calls) == 3
