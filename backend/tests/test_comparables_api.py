"""M6 comparable pace–heart-rate analysis."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity
from app.utils import utcnow


def _seed() -> None:
    session = get_session_factory()()
    now = utcnow()
    try:
        session.add(
            Activity(
                fingerprint="m6-anchor-10k",
                name="Anchor 10K",
                sport="running",
                start_time_utc=now - timedelta(days=120),
                distance_m=10000,
                duration_s=3000,
                avg_hr=180,
                max_hr=192,
                is_race=True,
                has_streams=True,
                has_gps=True,
            )
        )
        # First block: 6:00/km at 145 bpm.
        for index, days in enumerate((100, 90, 80, 70)):
            session.add(
                Activity(
                    fingerprint=f"m6-early-{index}",
                    name=f"Early {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=days),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=145,
                    max_hr=185,
                    elevation_gain_m=20,
                )
            )
        # Recent block: 5:40/km at the same heart rate.
        for index, days in enumerate((35, 25, 15, 5)):
            session.add(
                Activity(
                    fingerprint=f"m6-recent-{index}",
                    name=f"Recent {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=days),
                    distance_m=8000,
                    duration_s=2720,
                    avg_hr=145,
                    max_hr=185,
                    elevation_gain_m=20,
                )
            )
        # A hard session must be excluded from the aerobic comparison.
        session.add(
            Activity(
                fingerprint="m6-hard",
                name="Track intervals",
                sport="running",
                start_time_utc=now - timedelta(days=10),
                distance_m=8000,
                duration_s=2400,
                avg_hr=178,
                max_hr=192,
                elevation_gain_m=5,
            )
        )
        session.commit()
    finally:
        session.close()


def test_pace_hr_empty_database(client):
    response = client.get("/api/v1/comparables/pace-hr")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["conclusion"] == "insufficient_data"
    assert payload["sessions"] == 0
    assert payload["groups"] == []
    assert payload["primary_group"] is None
    assert "no_running_activities" in payload["warnings"]
    assert "no_comparable_sessions" in payload["warnings"]
    assert "pace_hr_is_observational" in payload["notes"]


def test_pace_hr_detects_faster_pace_at_same_heart_rate(client):
    _seed()
    # Build the 10K anchor before asking for the comparison.
    assert client.get("/api/v1/performance").status_code == 200

    response = client.get("/api/v1/comparables/pace-hr?days=180")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["conclusion"] == "faster_same_hr"
    assert payload["sessions"] == 8
    assert payload["excluded_races"] == 1
    assert payload["excluded_hard"] == 1
    assert payload["primary_group"] == "medium_flat"

    group = payload["groups"][0]
    assert group["key"] == "medium_flat"
    assert group["distance_band"] == "medium"
    assert group["terrain_band"] == "flat"
    assert group["sessions"] == 8
    assert group["reference_hr"] == 145
    assert group["early_pace_s_per_km"] == 360
    assert group["recent_pace_s_per_km"] == 340
    assert group["change_s_per_km"] == -20
    assert group["change_pct"] == -5.6
    assert group["status"] == "improving"
    assert group["confidence"] in {"low", "medium", "high"}
    assert len(group["points"]) == 8
    assert {point["period"] for point in group["points"]} == {"early", "recent"}
    assert "temperature_not_controlled" in group["reasons"]
    assert "races_excluded" in payload["notes"]
    assert "hard_sessions_excluded" in payload["notes"]


def test_pace_hr_without_heart_rate_is_explicit(client):
    session = get_session_factory()()
    try:
        session.add(
            Activity(
                fingerprint="m6-no-hr",
                name="No HR",
                sport="running",
                start_time_utc=utcnow() - timedelta(days=10),
                distance_m=8000,
                duration_s=2880,
                avg_hr=None,
                elevation_gain_m=10,
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.get("/api/v1/comparables/pace-hr")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["excluded_missing_hr"] == 1
    assert "no_hr" in payload["warnings"]
    assert "no_comparable_sessions" in payload["warnings"]
