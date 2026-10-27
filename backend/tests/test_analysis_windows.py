"""M16: configurable analysis windows and the diagnostics dimension trend."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db import get_session_factory
from app.models import Activity
from app.services.diagnostics import build_diagnostics, build_diagnostics_trend
from app.utils import utcnow

WEEKLY_SESSIONS = (
    (8000.0, 2880.0, 142, 165),
    (14000.0, 5400.0, 148, 172),
    (9000.0, 2520.0, 172, 188),
)


def _seed_training_history(reference: datetime) -> None:
    session = get_session_factory()()
    try:
        for week in range(12):
            for index, (distance_m, duration_s, avg_hr, max_hr) in enumerate(WEEKLY_SESSIONS):
                session.add(
                    Activity(
                        fingerprint=f"m16-{week}-{index}",
                        name=f"M16 week {week} session {index}",
                        sport="running",
                        start_time_utc=reference - timedelta(days=week * 7 + index * 2 + 1),
                        distance_m=distance_m,
                        duration_s=duration_s,
                        avg_hr=avg_hr,
                        max_hr=max_hr,
                        elevation_gain_m=20.0,
                        has_streams=True,
                        has_gps=True,
                    )
                )
        session.commit()
    finally:
        session.close()


def test_build_diagnostics_window_days_changes_coverage_not_scores(client):
    reference = datetime(2026, 10, 27, 12)
    _seed_training_history(reference)
    session = get_session_factory()()

    try:
        overviews = {
            days: build_diagnostics(session, reference, window_days=days) for days in (28, 56, 84)
        }
    finally:
        session.close()

    for days, overview in overviews.items():
        assert overview.window_days == days
        assert overview.coverage.window_weeks == days // 7
        assert len(overview.dimensions) == 6
        assert all(dimension.score is not None for dimension in overview.dimensions)
        assert overview.status in {"ok", "strong"}

    # Longer windows include at least the activities of shorter ones.
    assert (
        overviews[28].coverage.activities
        <= overviews[56].coverage.activities
        <= overviews[84].coverage.activities
    )


def test_diagnostics_trend_returns_six_dimensions_and_windows(client):
    _seed_training_history(utcnow())

    response = client.get("/api/v1/diagnostics/trend?tz_offset_minutes=0")
    assert response.status_code == 200
    payload = response.json()

    assert payload["current_window_days"] == 84
    assert payload["windows"] == [28, 56, 84]
    assert {item["key"] for item in payload["dimensions"]} == {
        "volume",
        "consistency",
        "intensity",
        "load",
        "recovery",
        "specificity",
    }
    assert payload["overall"]["key"] == "overall"

    for series in [*payload["dimensions"], payload["overall"]]:
        assert [point["window_days"] for point in series["windows"]] == [28, 56, 84]
        assert series["current"]["window_days"] == 84
        assert series["trend"] in {"improving", "stable", "worsening", "unknown"}
        for point in series["windows"]:
            assert point["window_weeks"] == point["window_days"] // 7
            assert point["confidence"] in {"low", "medium", "high"}
            assert point["status"]
            if point["window_days"] == 84:
                assert point["delta"] is None
            elif point["score"] is not None and series["current"]["score"] is not None:
                assert point["delta"] == pytest.approx(
                    series["current"]["score"] - point["score"],
                    abs=0.1,
                )

    assert any(series["current"]["score"] is not None for series in payload["dimensions"])
    assert "windows_overlap" in payload["notes"]
    assert "delta_threshold_5_points" in payload["notes"]


def test_diagnostics_trend_marks_missing_scores_without_inventing(client):
    response = client.get("/api/v1/diagnostics/trend")
    assert response.status_code == 200
    payload = response.json()

    for series in payload["dimensions"]:
        assert all(point["score"] is None for point in series["windows"])
        assert all(point["status"] == "unknown" for point in series["windows"])
        assert series["current"]["score"] is None
        assert series["delta"] is None
        assert series["trend"] == "unknown"

    assert payload["overall"]["current"]["score"] is None
    assert payload["overall"]["trend"] == "unknown"
    assert "partial_window_data" in payload["warnings"]
    assert "no_current_score" in payload["warnings"]


def test_diagnostics_trend_service_matches_endpoint(client):
    _seed_training_history(utcnow())
    session = get_session_factory()()
    try:
        trend = build_diagnostics_trend(session, tz_offset_minutes=0)
    finally:
        session.close()

    assert trend.current_window_days == 84
    assert len(trend.dimensions) == 6
    assert len(trend.overall.windows) == 3


@pytest.mark.parametrize("days", [7, 28, 56, 84, 365, 730])
def test_progress_accepts_short_and_long_windows(client, days):
    response = client.get(f"/api/v1/progress?days={days}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["window_days"] == days
    assert payload["consistency"]["window_days"] == days
    assert len(payload["weeks"]) >= days // 7
    assert payload["totals"]["sessions"] == 0
    assert payload["status"] == "insufficient"


@pytest.mark.parametrize("days", [6, 731])
def test_progress_rejects_windows_outside_limits(client, days):
    assert client.get(f"/api/v1/progress?days={days}").status_code == 422


def test_existing_diagnostics_and_progress_defaults_are_unchanged(client):
    diagnostics = client.get("/api/v1/diagnostics").json()
    progress = client.get("/api/v1/progress").json()

    assert diagnostics["window_days"] == 84
    assert diagnostics["coverage"]["window_weeks"] == 12
    assert progress["window_days"] == 180
    assert diagnostics["status"] == "insufficient"
    assert progress["status"] == "insufficient"
