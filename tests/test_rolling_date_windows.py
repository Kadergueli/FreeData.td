"""Patch 0037 — collectors must not use frozen date windows (they silently stopped at 2024)."""
import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.agents import base
from app.agents.base import nasa_power_years, recent_window, wb_years

AGENTS = sorted(Path(base.__file__).parent.glob("*.py"))
WINDOW_KEYS = {"start", "end", "start_date", "end_date", "startDate", "endDate", "date"}


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_no_literal_date_window_in_request_params(path):
    """No `{"start_date": "2024-01-01"}`-style literal in any request parameter dict."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value in WINDOW_KEYS
                        and isinstance(value, ast.Constant) and isinstance(value.value, str)
                        and any(ch.isdigit() for ch in value.value)):
                    offenders.append((key.value, value.value, node.lineno))
    assert not offenders, f"frozen date window(s) in {path.name}: {offenders}"


class _Clock(datetime):
    fixed = datetime(2027, 3, 5, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.fixed


def test_windows_follow_the_calendar(monkeypatch):
    monkeypatch.setattr(base, "datetime", _Clock)
    assert wb_years(2015) == "2015:2027"
    assert nasa_power_years(5) == ("2023", "2027")
    start, end = recent_window(months=6)
    assert end == "2027-02-26" and start == "2026-08-01"
    assert recent_window(months=12) == ("2026-02-01", "2027-02-26")
    assert recent_window(months=24, lag_days=0) == ("2025-03-01", "2027-03-05")


def test_window_is_valid_today():
    start, end = recent_window(months=6)
    assert date.fromisoformat(start) < date.fromisoformat(end) <= datetime.now(UTC).date()
