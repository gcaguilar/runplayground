"""M5 weekly briefing API."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, PerformanceSnapshot, RaceGoal
from app.utils import utcnow


def _seed() -> None:
    session = get_session_factory()()
    now = utcnow()
    try:
        session.add_all(
            [
                Activity(
                    fingerprint="m5-brief-10k",
                    name="Autumn 10K",
                    sport="running",
                    start_time_utc=now - timedelta(days=14),
                    distance_m=10000,
                    duration_s=3000,
                    avg_hr=176,
                    max_hr=190,
                    is_race=True,
                    has_streams=True,
                    has_gps=True,
                ),
                Activity(
                    fingerprint="m5-brief-5k",
                    name="Park 5K",
                    sport="running",
                    start_time_utc=now - timedelta(days=21),
                    distance_m=5000,
                    duration_s=1500,
                    avg_hr=180,
                    max_hr=192,
                    is_race=True,
                    has_gps=True,
                ),
            ]
        )
        for index in range(8):
            session.add(
                Activity(
                    fingerprint=f"m5-brief-easy-{index}",
                    name=f"Easy {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=3 + index * 4),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=142,
                )
            )
        for days, fitness in ((30, 3045.0), (60, 3060.0), (90, 3025.0)):
            session.add(
                PerformanceSnapshot(
                    snapshot_date=(now - timedelta(days=days)).date(),
                    computed_at=now - timedelta(days=days),
                    model_version="m1.0",
                    fitness_anchor_s=fitness,
                    fitness_anchor_low_s=fitness - 50,
                    fitness_anchor_high_s=fitness + 50,
                    fitness_confidence="medium",
                    predictions=[
                        {
                            "distance_key": "10k",
                            "distance_m": 10000.0,
                            "planning_s": fitness,
                            "planning_low_s": fitness - 50,
                            "planning_high_s": fitness + 50,
                            "confidence": "medium",
                        }
                    ],
                )
            )
        session.add(
            RaceGoal(
                distance_m=10000,
                target_time_s=2940,
                target_date=(now + timedelta(days=70)).date(),
                race_name="City 10K",
            )
        )
        session.commit()
    finally:
        session.close()


def test_briefing_empty_database(client):
    response = client.get("/api/v1/briefing")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["headline"] == "insufficient_data"
    assert payload["fitness_anchor"] is None
    assert len(payload["trends"]) == 3
    assert all(item["status"] == "unknown" for item in payload["trends"])
    assert len(payload["distances"]) == 4
    assert all(item["time_s"] is None for item in payload["distances"])
    assert len(payload["signals"]) == 6
    assert "no_activities" in payload["warnings"]
    assert "no_predictions" in payload["warnings"]
    assert payload["action"] is None


def test_briefing_composes_fitness_predictions_and_actions(client):
    _seed()

    response = client.get("/api/v1/briefing")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] in {"ok", "partial"}
    assert payload["fitness_anchor"] is not None
    assert payload["fitness_anchor"]["distance_m"] == 10000
    assert payload["confidence"] in {"low", "medium", "high"}

    trends = {item["window_days"]: item for item in payload["trends"]}
    assert set(trends) == {28, 56, 84}
    assert any(item["status"] != "unknown" for item in trends.values())
    assert trends[28]["previous_s"] is not None
    assert trends[28]["change_s"] is not None
    assert trends[28]["status"] in {"improving", "stable", "worsening"}

    distances = {item["distance_key"]: item for item in payload["distances"]}
    assert set(distances) == {"5k", "10k", "half_marathon", "marathon"}
    ten = distances["10k"]
    assert ten["time_s"] is not None
    assert ten["low_s"] <= ten["time_s"] <= ten["high_s"]
    assert ten["goal_time_s"] == 2940
    assert ten["goal_gap_s"] is not None

    signals = {item["key"]: item for item in payload["signals"]}
    assert {"volume", "consistency", "load", "recovery", "specificity"}.issubset(signals)
    assert all(item["confidence"] in {"low", "medium", "high"} for item in signals.values())

    assert payload["headline"] in {
        "improving_with_limit",
        "improving_balanced",
        "stable_with_limit",
        "stable_balanced",
        "worsening_with_limit",
        "worsening_balanced",
        "no_trend_with_limit",
        "no_trend_balanced",
        "no_recent_training",
    }
    if payload["limitation"] is not None:
        assert payload["action"] is not None
        assert payload["action"]["dimension_key"] == payload["limitation"]["dimension_key"]
        assert payload["headline_params"].get("limiter") == payload["limitation"]["dimension_key"]

    assert "briefing_is_derived" in payload["notes"]
    assert "not_medical_advice" in payload["notes"]
