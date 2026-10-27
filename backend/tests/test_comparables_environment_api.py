"""M18 environmental context in the pace–heart-rate comparison."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, StreamSample
from app.utils import utcnow


def _seed_run(
    index: int,
    *,
    days_ago: int,
    pace_s_per_km: float,
    elevation_gain_m: float | None,
    temperatures: list[float] | None = None,
    avg_hr: int = 145,
) -> int:
    session = get_session_factory()()
    try:
        distance_m = 8000.0
        activity = Activity(
            fingerprint=f"m18-{index}-{days_ago}",
            name=f"M18 run {index}",
            sport="running",
            start_time_utc=utcnow() - timedelta(days=days_ago),
            distance_m=distance_m,
            duration_s=pace_s_per_km * (distance_m / 1000.0),
            avg_hr=avg_hr,
            max_hr=185,
            elevation_gain_m=elevation_gain_m,
            has_streams=bool(temperatures),
            has_gps=bool(temperatures),
        )
        session.add(activity)
        session.flush()
        for sample_index, temperature in enumerate(temperatures or []):
            session.add(
                StreamSample(
                    activity_id=activity.id,
                    sample_index=sample_index,
                    distance_m=sample_index * 500.0,
                    elapsed_s=sample_index * 180.0,
                    heart_rate=avg_hr,
                    temperature_c=temperature,
                )
            )
        session.commit()
        return activity.id
    finally:
        session.close()


def _seed_block(
    prefix: str,
    *,
    days: tuple[int, ...],
    pace_s_per_km: float,
    elevation_gain_m: float | None,
    temperatures: list[float] | None = None,
) -> list[int]:
    return [
        _seed_run(
            index=f"{prefix}-{position}",
            days_ago=day,
            pace_s_per_km=pace_s_per_km,
            elevation_gain_m=elevation_gain_m,
            temperatures=temperatures,
        )
        for position, day in enumerate(days)
    ]


def _analysis(client) -> dict:
    response = client.get("/api/v1/comparables/pace-hr?days=180")
    assert response.status_code == 200
    return response.json()


def test_missing_temperature_keeps_the_raw_pace_and_warns(client):
    _seed_block("early", days=(100, 90, 80, 70), pace_s_per_km=360, elevation_gain_m=60)
    _seed_block("recent", days=(35, 25, 15, 5), pace_s_per_km=340, elevation_gain_m=60)

    payload = _analysis(client)
    group = payload["groups"][0]
    point = group["points"][0]

    assert payload["temperature_sessions"] == 0
    assert payload["temperature_c"] is None
    assert payload["temperature_adjusted"] is False
    assert payload["terrain_adjusted"] is True
    assert "temperature_not_available" in payload["warnings"]
    assert "temperature_not_available" in payload["notes"]
    assert "temperature_not_controlled" in payload["notes"]
    assert "temperature_not_available" in group["reasons"]
    assert point["temperature_c"] is None
    assert point["temperature_samples"] == 0
    assert point["heat_adjustment_s_per_km"] == 0.0
    # 60 m / 8 km = 7.5 m/km → 7.5 s/km of estimated terrain cost.
    assert point["elevation_per_km_m"] == 7.5
    assert point["terrain_adjustment_s_per_km"] == 7.5
    assert point["environment_adjusted_pace_s_per_km"] == round(360 - 7.5, 1)


def test_heat_adjustment_is_applied_and_capped(client):
    _seed_block(
        "early",
        days=(100, 90, 80, 70),
        pace_s_per_km=360,
        elevation_gain_m=None,
        temperatures=[30.0],
    )
    _seed_block(
        "recent",
        days=(35, 25, 15, 5),
        pace_s_per_km=360,
        elevation_gain_m=None,
        temperatures=[45.0],
    )

    payload = _analysis(client)
    group = payload["groups"][0]
    points = {point["period"]: point for point in group["points"]}

    # 30 °C: 15 °C above the baseline × 0.3 % = 4.5 % of 360 s/km.
    assert points["early"]["heat_adjustment_s_per_km"] == 16.2
    # 45 °C would be 9 %, capped at 6 % of 360 s/km.
    assert points["recent"]["heat_adjustment_s_per_km"] == 21.6
    assert group["temperature_adjusted"] is True
    assert group["temperature_c"] == 37.5
    assert group["temperature_sessions"] == 8
    assert "heat_adjustment_applied" in payload["notes"]
    assert "temperature_from_streams" in payload["notes"]
    assert "temperature_not_controlled" not in payload["notes"]


def test_environment_adjusted_change_uses_heat_and_ignores_raw_equality(client):
    _seed_block(
        "early",
        days=(100, 90, 80, 70),
        pace_s_per_km=360,
        elevation_gain_m=None,
        temperatures=[30.0],
    )
    _seed_block(
        "recent",
        days=(35, 25, 15, 5),
        pace_s_per_km=360,
        elevation_gain_m=None,
        temperatures=[15.0],
    )

    payload = _analysis(client)
    group = payload["groups"][0]

    # Raw pace is identical in both blocks.
    assert group["raw_early_pace_s_per_km"] == 360
    assert group["raw_recent_pace_s_per_km"] == 360
    # The env-adjusted pace removes the heat cost from the early block, so the
    # normalised comparison is slower, not equal.
    assert group["environment_early_pace_s_per_km"] == 343.8
    assert group["environment_recent_pace_s_per_km"] == 360.0
    assert group["environment_change_s_per_km"] == 16.2
    assert group["change_s_per_km"] == 16.2
    assert group["status"] == "worsening"


def test_terrain_adjustment_is_conservative_and_capped(client):
    _seed_block(
        "early",
        days=(100, 90, 80, 70),
        pace_s_per_km=360,
        elevation_gain_m=400,
    )
    _seed_block(
        "recent",
        days=(35, 25, 15, 5),
        pace_s_per_km=360,
        elevation_gain_m=400,
    )

    payload = _analysis(client)
    group = payload["groups"][0]
    point = group["points"][0]

    # 400 m / 8 km = 50 m/km, which would be 50 s/km without the cap.
    assert point["elevation_per_km_m"] == 50.0
    assert point["terrain_adjustment_s_per_km"] == 25.0
    assert group["avg_terrain_adjustment_s_per_km"] == 25.0
    assert group["terrain_adjusted"] is True
    assert payload["avg_terrain_adjustment_s_per_km"] == 25.0
    assert "terrain_adjustment_estimated" in payload["notes"]


def test_temperature_average_uses_one_plausible_stream_aggregate(client):
    _seed_block(
        "early",
        days=(100, 90, 80, 70),
        pace_s_per_km=360,
        elevation_gain_m=20,
        temperatures=[10.0, 20.0, 30.0, 99.0, -50.0],
    )
    _seed_block(
        "recent",
        days=(35, 25, 15, 5),
        pace_s_per_km=340,
        elevation_gain_m=20,
        temperatures=[20.0],
    )

    payload = _analysis(client)
    group = payload["groups"][0]
    early = next(point for point in group["points"] if point["period"] == "early")

    # Only 10, 20 and 30 °C are plausible; 99 and -50 are discarded before the mean.
    assert early["temperature_c"] == 20.0
    assert early["temperature_samples"] == 3
    assert group["temperature_sessions"] == 8
    assert group["temperature_coverage"] == 1.0
    assert payload["temperature_sessions"] == 8
    assert payload["temperature_coverage"] == 1.0


def test_without_streams_the_contract_stays_compatible(client):
    _seed_block("early", days=(100, 90, 80, 70), pace_s_per_km=360, elevation_gain_m=20)
    _seed_block("recent", days=(35, 25, 15, 5), pace_s_per_km=340, elevation_gain_m=20)

    payload = _analysis(client)
    group = payload["groups"][0]
    point = group["points"][0]

    # Existing fields keep their meaning and the new ones default cleanly.
    assert point["adjusted_pace_s_per_km"] is not None
    assert point["environment_adjusted_pace_s_per_km"] is not None
    assert point["environment_hr_adjusted_pace_s_per_km"] is not None
    assert point["temperature_samples"] == 0
    assert group["confidence_score"] <= 0.92
    assert payload["model_version"] == "m18.0"
