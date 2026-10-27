"""M4 future-scenario API: conservative, explicit and bounded."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, RaceGoal
from app.utils import utcnow


def _seed() -> None:
    session = get_session_factory()()
    now = utcnow()
    try:
        session.add_all(
            [
                Activity(
                    fingerprint="m4-forecast-10k",
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
                    fingerprint="m4-forecast-5k",
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
                    fingerprint=f"m4-forecast-easy-{index}",
                    name=f"Easy {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=3 + index * 4),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=142,
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


def test_forecast_empty_database(client):
    response = client.get("/api/v1/forecast?weeks=8")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["weeks"] == 8
    assert payload["focus_distance_key"] == "10k"
    assert payload["focus_source"] == "default"
    assert payload["baseline"]["anchor_time_s"] is None
    assert len(payload["scenarios"]) == 4
    assert all(item["anchor_time_s"] is None for item in payload["scenarios"])
    assert "no_anchor" in payload["warnings"]
    assert "simulation_not_forecast" in payload["notes"]


def test_forecast_returns_four_explicit_scenarios(client):
    _seed()

    response = client.get("/api/v1/forecast?weeks=8")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["focus_distance_key"] == "10k"
    assert payload["focus_source"] == "goal"
    assert payload["baseline"]["anchor_time_s"] is not None
    assert payload["training"]["weekly_avg_m"] > 0
    assert "no_anchor" not in payload["warnings"]

    scenarios = {item["key"]: item for item in payload["scenarios"]}
    assert set(scenarios) == {"maintain", "consistency", "specificity", "recovery"}

    maintain = scenarios["maintain"]
    assert maintain["delta_s"] == 0
    assert maintain["effect_pct"] == 0
    assert "current_training" in maintain["assumptions"]
    assert maintain["anchor_time_s"] == payload["baseline"]["anchor_time_s"]

    consistency = scenarios["consistency"]
    assert "more_regular_weeks" in consistency["assumptions"]
    assert consistency["anchor_time_s"] is not None
    assert consistency["effect_pct"] >= 0
    assert consistency["anchor_low_s"] <= consistency["anchor_time_s"]
    assert consistency["anchor_time_s"] <= consistency["anchor_high_s"]

    specificity = scenarios["specificity"]
    assert "gradual_specific_build" in specificity["assumptions"]
    assert specificity["anchor_time_s"] is not None
    assert specificity["effect_pct"] >= 0
    assert any(
        item["distance_key"] == "10k" and item["time_s"] is not None
        for item in specificity["distances"]
    )

    recovery = scenarios["recovery"]
    # A deload can recover fatigue or cost a little fitness. It must never be
    # sold as a guaranteed improvement, and both directions stay small.
    assert recovery["effect_pct"] is not None
    assert -1.0 <= recovery["effect_pct"] <= 1.5
    if "no_fatigue_to_recover" in recovery["confidence_reasons"]:
        assert recovery["effect_pct"] <= 0
        assert "deload_can_reduce_fitness" in recovery["notes"]

    for item in payload["scenarios"]:
        assert item["confidence"] in {"low", "medium", "high"}
        assert item["confidence_score"] <= 0.95
        assert "simulation_not_forecast" in item["confidence_reasons"]
        assert len(item["distances"]) == 4
        assert item["notes"]
        assert item["evidence"]


def test_forecast_horizon_is_bounded_and_validated(client):
    _seed()

    eight = client.get("/api/v1/forecast?weeks=8").json()
    twelve = client.get("/api/v1/forecast?weeks=12").json()

    assert eight["weeks"] == 8
    assert twelve["weeks"] == 12
    eight_specificity = next(item for item in eight["scenarios"] if item["key"] == "specificity")
    twelve_specificity = next(item for item in twelve["scenarios"] if item["key"] == "specificity")
    assert abs(twelve_specificity["effect_pct"]) >= abs(eight_specificity["effect_pct"])

    for item in twelve["scenarios"]:
        assert item["anchor_low_s"] is not None
        assert item["anchor_high_s"] is not None
        assert item["anchor_low_s"] <= item["anchor_time_s"] <= item["anchor_high_s"]

    assert client.get("/api/v1/forecast?weeks=7").status_code == 422
    assert client.get("/api/v1/forecast?weeks=13").status_code == 422
