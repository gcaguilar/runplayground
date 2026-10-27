from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from app.db import get_session_factory
from app.models import Activity, StreamSample


def _seed_activity(
    *,
    sport: str = "running",
    duration_s: float = 600.0,
    avg_hr: int | None = None,
    max_hr: int | None = None,
    heart_rates: Iterable[int | None] = (),
    step_s: float = 1.0,
    elapsed: bool = True,
) -> int:
    session = get_session_factory()()
    try:
        activity = Activity(
            fingerprint=f"m17-{sport}-{datetime.now(UTC).timestamp()}-{id(heart_rates)}",
            name="M17 zone run",
            sport=sport,
            start_time_utc=datetime(2026, 10, 20, 7, 0, tzinfo=UTC),
            distance_m=5000,
            duration_s=duration_s,
            avg_hr=avg_hr,
            max_hr=max_hr,
            has_streams=bool(list(heart_rates)),
        )
        session.add(activity)
        session.flush()
        for index, heart_rate in enumerate(heart_rates):
            timestamp = (
                datetime(2026, 10, 20, 7, 0, tzinfo=UTC) + timedelta(seconds=index * step_s)
                if not elapsed
                else None
            )
            session.add(
                StreamSample(
                    activity_id=activity.id,
                    sample_index=index,
                    elapsed_s=index * step_s if elapsed else None,
                    timestamp_utc=timestamp,
                    distance_m=index * 2.5,
                    heart_rate=heart_rate,
                )
            )
        session.commit()
        return activity.id
    finally:
        session.close()


def _zones(client, activity_id: int) -> dict:
    response = client.get(f"/api/v1/activities/{activity_id}/zones")
    assert response.status_code == 200
    return response.json()


def test_zones_use_manual_max_hr_and_sum_to_the_valid_time(client):
    client.put("/api/v1/analysis/settings", json={"max_hr": 200})
    activity_id = _seed_activity(
        heart_rates=[100, 125, 130, 145, 150, 165, 170, 182, 185, 190],
        avg_hr=150,
        max_hr=190,
    )

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["method"] == "max_hr"
    assert payload["source"] == "manual"
    assert payload["reference_bpm"] == 200
    assert payload["cuts_bpm"] == [120, 140, 160, 180]
    assert payload["cuts_pct"] == [60.0, 70.0, 80.0, 90.0]
    assert [zone["key"] for zone in payload["zones"]] == ["z1", "z2", "z3", "z4", "z5"]
    assert payload["avg_hr"] == 150
    assert payload["avg_hr_source"] == "activity"
    assert payload["max_hr"] == 190
    assert payload["max_hr_source"] == "activity"
    assert payload["samples_with_hr"] == 10
    assert payload["coverage"] == 1.0
    assert round(sum(zone["percentage"] for zone in payload["zones"]), 1) == 100.0
    assert abs(payload["total_hr_s"] - 10.0) < 0.01


def test_zones_use_manual_threshold_hr_and_explicit_cuts(client):
    client.put("/api/v1/analysis/settings", json={"threshold_hr": 180})
    activity_id = _seed_activity(
        heart_rates=[140, 145, 150, 165, 170, 182, 185, 188, 192, 200],
        max_hr=200,
    )

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["method"] == "threshold_hr"
    assert payload["source"] == "manual"
    assert payload["reference_bpm"] == 180
    assert payload["cuts_bpm"] == [144, 162, 180, 189]
    assert payload["cuts_pct"] == [80.0, 90.0, 100.0, 105.0]
    assert "threshold_reference" in payload["notes"]
    assert round(sum(zone["percentage"] for zone in payload["zones"]), 1) == 100.0


def test_zones_fall_back_to_the_activity_stream_maximum(client):
    activity_id = _seed_activity(
        heart_rates=[120, 130, 145, 160, 175, 185],
        max_hr=None,
        avg_hr=None,
    )

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["method"] == "max_hr"
    assert payload["source"] == "activity_fallback"
    assert payload["reference_bpm"] == 185
    assert payload["stream_max_hr"] == 185
    assert payload["max_hr"] == 185
    assert payload["max_hr_source"] == "stream"
    assert "estimated_max_hr" in payload["warnings"]
    assert payload["cuts_bpm"] == [111, 130, 148, 167]


def test_zones_without_streams_are_insufficient_and_empty(client):
    activity_id = _seed_activity(heart_rates=[], max_hr=185)

    payload = _zones(client, activity_id)

    assert payload["status"] == "insufficient"
    assert payload["zones"] == []
    assert payload["cuts_bpm"] == []
    assert payload["reference_bpm"] == 185
    assert payload["source"] == "observed"
    assert "no_streams" in payload["warnings"]
    assert payload["total_hr_s"] == 0


def test_zones_without_heart_rate_are_insufficient(client):
    client.put("/api/v1/analysis/settings", json={"max_hr": 190})
    activity_id = _seed_activity(heart_rates=[None, None, None, None], max_hr=None)

    payload = _zones(client, activity_id)

    assert payload["status"] == "insufficient"
    assert payload["zones"] == []
    assert payload["samples_timed"] == 4
    assert payload["samples_with_hr"] == 0
    assert "no_hr" in payload["warnings"]


def test_low_coverage_adds_a_warning_but_keeps_measured_zones(client):
    client.put("/api/v1/analysis/settings", json={"max_hr": 200})
    heart_rates = [150] * 25 + [None] * 75
    activity_id = _seed_activity(heart_rates=heart_rates)

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["samples_with_hr"] == 25
    assert payload["samples_timed"] == 100
    assert payload["coverage"] == 0.25
    assert "low_coverage" in payload["warnings"]
    assert round(sum(zone["percentage"] for zone in payload["zones"]), 1) == 100.0


def test_cuts_are_ordered_and_zone_percentages_sum_to_one_hundred(client):
    client.put("/api/v1/analysis/settings", json={"max_hr": 197})
    activity_id = _seed_activity(
        heart_rates=[95, 118, 120, 138, 140, 158, 160, 177, 179, 196],
        max_hr=196,
    )

    payload = _zones(client, activity_id)
    zones = payload["zones"]
    cuts = payload["cuts_bpm"]

    assert cuts == sorted(cuts)
    assert len(set(cuts)) == len(cuts)
    for previous, current in zip(cuts, cuts[1:], strict=False):
        assert previous < current
    for left, right in zip(zones, zones[1:], strict=False):
        assert left["upper_bpm"] == right["lower_bpm"]
    assert zones[-1]["upper_bpm"] == 230
    assert round(sum(zone["percentage"] for zone in zones), 1) == 100.0


def test_out_of_range_heart_rate_is_ignored_and_reported(client):
    client.put("/api/v1/analysis/settings", json={"max_hr": 200})
    activity_id = _seed_activity(
        heart_rates=[20, 150, 150, 250, 150, 150],
        max_hr=200,
    )

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["samples_with_hr"] == 4
    assert payload["samples_total"] == 6
    assert "hr_filtered" in payload["warnings"]
    assert abs(payload["total_hr_s"] - 4.0) < 0.01
    assert payload["zones"][2]["seconds"] == 4.0


def test_cuts_stay_strictly_increasing_at_the_physiological_ceiling(client):
    client.put("/api/v1/analysis/settings", json={"threshold_hr": 230})
    activity_id = _seed_activity(heart_rates=[220, 225, 229, 230, 230], max_hr=230)

    payload = _zones(client, activity_id)

    assert payload["status"] == "ok"
    assert payload["cuts_bpm"] == [184, 207, 229, 230]
    assert len(set(payload["cuts_bpm"])) == 4
    assert round(sum(zone["percentage"] for zone in payload["zones"]), 1) == 100.0


def test_zones_endpoint_returns_404_for_unknown_activity(client):
    assert client.get("/api/v1/activities/9999/zones").status_code == 404
