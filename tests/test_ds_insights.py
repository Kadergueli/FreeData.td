"""Tests for app/agents/ds_insights.py — had zero test coverage before this
pass, which is exactly how the soudure-threshold inversion bug went unnoticed.
"""

from datetime import UTC, datetime, timedelta

from app.agents.ds_insights import (
    compute_cross_sector_correlations,
    compute_freshness_scores,
    compute_seasonal_anomalies,
    compute_spatial_coverage,
)


def _obs(sector, value, days_ago=0, region="national", indicator="Test", month=None):
    if month is not None:
        ref_date = f"2024-{month:02d}-15"
    else:
        ref_date = (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat()
    return {
        "sector": sector, "value": value, "region": region,
        "indicator": indicator, "reference_date": ref_date,
        "unit": "units", "source": "Test",
    }


# ─── compute_freshness_scores ───────────────────────────────────────────────

def test_freshness_fresh_status_within_7_days():
    obs = [_obs("health", 1.0, days_ago=2)]
    result = compute_freshness_scores(obs)
    assert result["health"]["status"] == "fresh"
    assert result["health"]["days_ago"] == 2


def test_freshness_outdated_status_beyond_90_days():
    obs = [_obs("energy", 1.0, days_ago=200)]
    result = compute_freshness_scores(obs)
    assert result["energy"]["status"] == "outdated"


def test_freshness_no_data_for_sector_with_no_observations():
    result = compute_freshness_scores([])
    assert result["agriculture"]["status"] == "no_data"
    assert result["agriculture"]["last_date"] is None


def test_freshness_keeps_the_most_recent_date_per_sector():
    obs = [_obs("markets", 1.0, days_ago=10), _obs("markets", 2.0, days_ago=1)]
    result = compute_freshness_scores(obs)
    assert result["markets"]["days_ago"] == 1


# ─── compute_cross_sector_correlations ──────────────────────────────────────

def test_correlation_insufficient_data_when_fewer_than_4_months():
    obs = [_obs("environment", 10, month=1), _obs("markets", 20, month=1)]
    results = compute_cross_sector_correlations(obs)
    env_markets = next(r for r in results if r["sector_a"] == "environment" and r["sector_b"] == "markets")
    assert env_markets["strength"] == "insufficient_data"
    assert env_markets["correlation"] is None


def test_correlation_detects_strong_positive_relationship():
    obs = []
    for i, month in enumerate([1, 2, 3, 4, 5, 6]):
        obs.append(_obs("environment", 10 + i * 5, month=month))
        obs.append(_obs("markets", 20 + i * 5, month=month))
    results = compute_cross_sector_correlations(obs)
    env_markets = next(r for r in results if r["sector_a"] == "environment" and r["sector_b"] == "markets")
    assert env_markets["correlation"] > 0.8
    assert env_markets["strength"] == "strong"


# ─── compute_spatial_coverage ────────────────────────────────────────────────

def test_spatial_coverage_extracts_province_from_city_format():
    obs = [_obs("agriculture", 1.0, region="Moundou (Logone Occidental)")]
    result = compute_spatial_coverage(obs)
    assert "Logone Occidental" in result["regions_covered"]


def test_spatial_coverage_ignores_national_placeholder():
    obs = [_obs("agriculture", 1.0, region="national")]
    result = compute_spatial_coverage(obs)
    assert result["total_regions"] == 0


def test_spatial_coverage_rate_is_bounded_to_one():
    obs = [_obs("agriculture", 1.0, region=f"Region{i}") for i in range(50)]
    result = compute_spatial_coverage(obs)
    assert result["coverage_rate"] <= 1.0


# ─── compute_seasonal_anomalies — the actual bug fixed in this pass ─────────

def test_soudure_threshold_is_higher_not_lower(monkeypatch):
    """Regression test for the inverted-threshold bug: during soudure
    (Jun-Sep), agriculture/markets anomaly detection must use a HIGHER
    threshold (less sensitive), not lower - normal seasonal price variance
    must not get flagged as an anomaly. Verified by intercepting the actual
    threshold value passed to the scoring function, rather than inferring it
    indirectly from anomaly counts (which turned out not to be sensitive
    enough to distinguish 2.5 from 3.5 for an extreme outlier)."""
    import app.agents.ds_insights as ds_insights_module

    captured_thresholds = []
    original = ds_insights_module._zscore_anomaly

    def spy(values, threshold=3.0):
        captured_thresholds.append(threshold)
        return original(values, threshold=threshold)

    monkeypatch.setattr(ds_insights_module, "_zscore_anomaly", spy)

    obs_soudure = [_obs("markets", v, month=7, indicator="Prix mil") for v in [100, 102, 98, 101, 99]]
    obs_normal = [_obs("markets", v, month=1, indicator="Prix mil") for v in [100, 102, 98, 101, 99]]
    obs_other_sector_soudure = [_obs("health", v, month=7, indicator="X") for v in [100, 102, 98, 101, 99]]

    compute_seasonal_anomalies(obs_soudure)
    soudure_threshold = captured_thresholds[-1]

    compute_seasonal_anomalies(obs_normal)
    normal_threshold = captured_thresholds[-1]

    compute_seasonal_anomalies(obs_other_sector_soudure)
    other_sector_threshold = captured_thresholds[-1]

    assert soudure_threshold > normal_threshold, (
        f"soudure threshold ({soudure_threshold}) must be HIGHER (less sensitive) than "
        f"the normal-period threshold ({normal_threshold}), not lower"
    )
    assert other_sector_threshold == normal_threshold, (
        "the relaxed soudure threshold must only apply to agriculture/markets, "
        "not to unrelated sectors during the same months"
    )


def test_seasonal_anomalies_requires_at_least_4_points():
    obs = [_obs("health", 100, month=3), _obs("health", 500, month=3)]
    anomalies = compute_seasonal_anomalies(obs)
    assert anomalies == []


def test_seasonal_anomalies_flags_clear_outlier():
    obs = [_obs("economy", v, month=3, indicator="PIB") for v in [100, 101, 99, 102, 1000]]
    anomalies = compute_seasonal_anomalies(obs)
    assert any(a["value"] == 1000 for a in anomalies)


# ─── GET /api/v1/insights/cross-sector — resilience regression ─────────────

def test_cross_sector_endpoint_degrades_gracefully_on_internal_error(monkeypatch):
    """Regression test for a NameError bug: main.py's cross_sector_insights()
    except-block referenced an undefined `logger`, so any internal failure
    crashed with an unhandled 500 instead of returning the intended safe
    defaults. This exercises the actual FastAPI route, not just the ds_insights
    module directly."""
    from fastapi.testclient import TestClient
    import app.main as main_module

    client = TestClient(main_module.app)

    def broken(*_a, **_kw):
        raise ValueError("simulated internal failure")

    monkeypatch.setattr(main_module.repository, "list_observations", broken)

    response = client.get("/api/v1/insights/cross-sector")

    assert response.status_code == 200
    body = response.json()
    assert body["freshness"] == {}
    assert body["correlations"] == []
    assert body["total_observations_analyzed"] == 0


def test_cross_sector_endpoint_returns_real_data_on_success():
    from fastapi.testclient import TestClient
    import app.main as main_module

    client = TestClient(main_module.app)
    response = client.get("/api/v1/insights/cross-sector")

    assert response.status_code == 200
    body = response.json()
    assert "freshness" in body
    assert "correlations" in body
    assert "spatial_coverage" in body
    assert "seasonal_anomalies" in body
