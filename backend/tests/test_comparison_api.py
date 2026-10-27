"""M7 workout comparison: metrics, splits and comparability caveats."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, StreamSample
from app.utils import utcnow


def _seed_activity(
    fingerprint: str,
    name: str,
    *,
    days_ago: int,
    distance_m: float = 10000,
    pace_s_per_km: float = 300,
    avg_hr: int | None = 150,
    elevation_gain_m: float | None = 50,
    has_streams: bool = True,
    sport: str = "running",
    sub_sport: str | None = None,
) -> int:
    session = get_session_factory()()
    now = utcnow()
    try:
        duration = distance_m / 1000 * pace_s_per_km
        activity = Activity(
            fingerprint=fingerprint,
            name=name,
            sport=sport,
            sub_sport=sub_sport,
            start_time_utc=now - timedelta(days=days_ago),
            distance_m=distance_m,
            duration_s=duration,
            avg_hr=avg_hr,
            max_hr=185 if avg_hr else None,
            avg_cadence_spm=170,
            elevation_gain_m=elevation_gain_m,
            has_streams=has_streams,
            has_gps=has_streams,
        )
        session.add(activity)
        session.flush()
        if has_streams:
            sample_index = 0
            distance = 0.0
            while distance <= distance_m:
                session.add(
                    StreamSample(
                        activity_id=activity.id,
                        sample_index=sample_index,
                        distance_m=distance,
                        elapsed_s=distance / 1000 * pace_s_per_km,
                        heart_rate=avg_hr,
                    )
                )
                sample_index += 1
                distance += 500.0
        session.commit()
        return activity.id
    finally:
        session.close()


def test_comparison_of_comparable_runs(client):
    left_id = _seed_activity("m7-left", "Morning 10K", days_ago=10, pace_s_per_km=300)
    right_id = _seed_activity(
        "m7-right",
        "Evening 10K",
        days_ago=3,
        pace_s_per_km=306,
        avg_hr=152,
        elevation_gain_m=55,
    )

    response = client.get(f"/api/v1/activities/compare?left_id={left_id}&right_id={right_id}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "comparable"
    assert payload["comparability"] >= 0.9
    assert payload["left"]["activity_id"] == left_id
    assert payload["right"]["activity_id"] == right_id

    metrics = {item["key"]: item for item in payload["metrics"]}
    pace = metrics["pace_s_per_km"]
    assert pace["left"] == 300
    assert pace["right"] == 306
    assert pace["delta"] == 6
    assert pace["better"] == "left"
    assert metrics["avg_hr"]["better"] == "similar"

    assert len(payload["splits"]) == 10
    first_split = payload["splits"][0]
    assert first_split["index"] == 1
    assert first_split["left_pace_s_per_km"] == 300
    assert first_split["right_pace_s_per_km"] == 306
    assert first_split["pace_delta_s"] == 6

    assert any(item["key"] == "slower_same_effort" for item in payload["insights"])
    assert "summary_metrics_only" in payload["notes"]


def test_comparison_rejects_unrelated_sessions(client):
    left_id = _seed_activity("m7-5k", "Park 5K", days_ago=5, distance_m=5000)
    right_id = _seed_activity(
        "m7-marathon",
        "Marathon",
        days_ago=20,
        distance_m=42195,
        pace_s_per_km=330,
    )

    payload = client.get(f"/api/v1/activities/compare?left_id={left_id}&right_id={right_id}").json()
    assert payload["status"] == "not_comparable"
    assert "distance_mismatch" in payload["reasons"]
    assert payload["insights"][0]["key"] == "comparison_not_comparable"


def test_comparison_handles_missing_streams_and_hr(client):
    left_id = _seed_activity(
        "m7-no-streams",
        "Treadmill",
        days_ago=2,
        has_streams=False,
        avg_hr=None,
    )
    right_id = _seed_activity("m7-streams", "Road 10K", days_ago=8)

    payload = client.get(f"/api/v1/activities/compare?left_id={left_id}&right_id={right_id}").json()
    assert payload["status"] == "limited"
    assert "missing_streams" in payload["warnings"]
    assert "missing_hr" in payload["warnings"]
    assert payload["splits"] == []
    assert "no_split_streams" in payload["notes"]


def test_comparison_validation(client):
    left_id = _seed_activity("m7-validation-left", "Left", days_ago=1)
    right_id = _seed_activity("m7-validation-right", "Right", days_ago=2)

    assert (
        client.get(f"/api/v1/activities/compare?left_id={left_id}&right_id={left_id}").status_code
        == 422
    )
    assert (
        client.get(f"/api/v1/activities/compare?left_id={left_id}&right_id=99999").status_code
        == 404
    )
    assert client.get("/api/v1/activities/compare?left_id=0&right_id=1").status_code == 422
    assert client.get("/api/v1/activities/compare").status_code == 422
    # The generic detail route still works and is not shadowed by /compare.
    assert client.get(f"/api/v1/activities/{right_id}").status_code == 200
