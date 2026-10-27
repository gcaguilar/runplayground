"""M4 tracking API: prediction accuracy, goal history and action follow-up."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, PerformanceSnapshot, RaceGoal
from app.utils import utcnow


def _snapshot(day, predictions):
    now = utcnow()
    return PerformanceSnapshot(
        snapshot_date=day,
        computed_at=now - timedelta(days=(now.date() - day).days),
        model_version="m1.0",
        fitness_anchor_s=2950.0,
        fitness_anchor_low_s=2880.0,
        fitness_anchor_high_s=3020.0,
        fitness_confidence="medium",
        predictions=predictions,
    )


def _predictions(ten_k: float, five_k: float):
    return [
        {
            "distance_key": "5k",
            "distance_m": 5000.0,
            "planning_s": five_k,
            "planning_low_s": five_k - 40,
            "planning_high_s": five_k + 40,
            "confidence": "medium",
        },
        {
            "distance_key": "10k",
            "distance_m": 10000.0,
            "planning_s": ten_k,
            "planning_low_s": ten_k - 50,
            "planning_high_s": ten_k + 50,
            "confidence": "medium",
        },
    ]


def _seed() -> dict[str, int]:
    session = get_session_factory()()
    now = utcnow()
    ids: dict[str, int] = {}
    try:
        ten_k = Activity(
            fingerprint="m4-track-10k",
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
        )
        five_k = Activity(
            fingerprint="m4-track-5k",
            name="Park 5K",
            sport="running",
            start_time_utc=now - timedelta(days=21),
            distance_m=5000,
            duration_s=1500,
            avg_hr=180,
            max_hr=192,
            is_race=True,
            has_gps=True,
        )
        session.add_all([ten_k, five_k])
        session.flush()
        ids["ten_k"] = ten_k.id
        ids["five_k"] = five_k.id

        for index in range(6):
            session.add(
                Activity(
                    fingerprint=f"m4-track-easy-{index}",
                    name=f"Easy {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=4 + index * 5),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=142,
                )
            )

        today = now.date()
        session.add_all(
            [
                _snapshot(today - timedelta(days=30), _predictions(2900.0, 1470.0)),
                _snapshot(today - timedelta(days=40), _predictions(2960.0, 1490.0)),
                _snapshot(today - timedelta(days=60), _predictions(2980.0, 1500.0)),
            ]
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
    return ids


def test_tracking_empty_database(client):
    response = client.get("/api/v1/tracking")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["accuracy"]["samples"] == []
    assert payload["accuracy"]["overall"] is None
    assert payload["goals"] == []
    assert payload["actions"] == []
    assert payload["suggestions"] == []
    assert "no_goals" in payload["warnings"]
    assert "no_accuracy_samples" in payload["warnings"]
    assert "accuracy_is_observational" in payload["notes"]


def test_tracking_matches_predictions_with_actual_results(client):
    ids = _seed()
    # Build best efforts before asking for accuracy.
    assert client.get("/api/v1/performance").status_code == 200

    response = client.get("/api/v1/tracking?days=180")
    assert response.status_code == 200
    payload = response.json()

    samples = payload["accuracy"]["samples"]
    assert samples
    assert payload["accuracy"]["overall"]["samples"] == len(samples)
    assert payload["accuracy"]["overall"]["mape_pct"] >= 0
    assert payload["accuracy"]["by_distance"]
    assert payload["accuracy"]["by_horizon"]
    assert payload["accuracy"]["overall"]["within_range_pct"] >= 0

    ten = next(
        item
        for item in samples
        if item["distance_key"] == "10k" and item["activity_id"] == ids["ten_k"]
    )
    assert ten["predicted_s"] == 2900
    assert ten["actual_s"] == 3000
    assert ten["error_s"] == 100
    assert ten["horizon_days"] == 16
    assert ten["is_race"] is True
    assert ten["within_range"] is False

    assert payload["status"] == "ok"
    assert payload["goals"]
    goal = payload["goals"][0]
    assert goal["distance_key"] == "10k"
    assert goal["target_time_s"] == 2940
    assert goal["current_time_s"] is not None
    assert goal["gap_s"] is not None
    assert goal["trend"] in {"improving", "stable", "worsening", "unknown"}
    assert len(goal["history"]) >= 3
    assert goal["last_reviewed_at"]
    results = goal["results"]
    assert results
    race = next(item for item in results if item["activity_id"] == ids["ten_k"])
    assert race["time_s"] == 3000
    assert race["is_race"] is True
    assert race["source"] == "race"
    assert "training_efforts_counted" in payload["accuracy"]["notes"]


def test_goal_revisions_are_append_only(client):
    _seed()
    client.get("/api/v1/performance")

    first = client.put(
        "/api/v1/performance/goals/10k",
        json={"target_time_s": 2940, "target_date": "2027-03-01", "race_name": "City 10K"},
    )
    assert first.status_code == 200

    same = client.put(
        "/api/v1/performance/goals/10k",
        json={"target_time_s": 2940, "target_date": "2027-03-01", "race_name": "City 10K"},
    )
    assert same.status_code == 200

    changed = client.put(
        "/api/v1/performance/goals/10k",
        json={"target_time_s": 2920, "target_date": "2027-03-01", "race_name": "City 10K"},
    )
    assert changed.status_code == 200

    tracking = client.get("/api/v1/tracking").json()
    goal = tracking["goals"][0]
    revisions = goal["revisions"]
    assert len(revisions) == 2
    assert revisions[0]["change_s"] is None
    assert revisions[1]["change_s"] == -20
    assert revisions[1]["target_time_s"] == 2920
    assert revisions[0]["prediction_time_s"] is not None


def test_tracked_actions_capture_a_baseline_and_follow_up(client):
    _seed()
    client.get("/api/v1/performance")

    created = client.put(
        "/api/v1/tracking/actions/specificity",
        json={"status": "in_progress", "note": "Add one long run per week"},
    )
    assert created.status_code == 200
    action = created.json()
    assert action["dimension_key"] == "specificity"
    assert action["status"] == "in_progress"
    assert action["note"] == "Add one long run per week"
    assert action["baseline_score"] is not None
    assert action["current_score"] is not None
    assert action["delta"] is not None
    assert action["verdict"] in {"improved", "stable", "worse", "unknown"}

    tracking = client.get("/api/v1/tracking").json()
    assert len(tracking["actions"]) == 1
    assert tracking["actions"][0]["dimension_key"] == "specificity"

    completed = client.put(
        "/api/v1/tracking/actions/specificity",
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert completed.json()["note"] is None

    assert (
        client.put(
            "/api/v1/tracking/actions/not-a-dimension",
            json={"status": "pending"},
        ).status_code
        == 404
    )
    assert client.delete("/api/v1/tracking/actions/specificity").status_code == 204
    assert client.delete("/api/v1/tracking/actions/specificity").status_code == 404


def test_progress_keeps_a_daily_snapshot(client):
    _seed()
    assert client.get("/api/v1/progress").status_code == 200

    history = client.get("/api/v1/performance/history?days=30").json()
    assert history["items"]
    today = utcnow().date().isoformat()
    assert any(item["date"] == today for item in history["items"])


def test_driver_analysis_finds_an_association_without_claiming_causality(client):
    from app.services.drivers import build_drivers

    session = get_session_factory()()
    now = utcnow()
    today = now.date()
    this_monday = today - timedelta(days=today.weekday())
    try:
        fitness = 3000.0
        volumes = [10, 20, 12, 24, 14, 22, 16, 26]
        for index, volume in enumerate(volumes):
            week = this_monday - timedelta(weeks=len(volumes) - index)
            if index > 0:
                improvement = 0.1 + (volume - 10) / 16 * 1.2
                fitness = fitness * (1 - improvement / 100)
            session.add(
                Activity(
                    fingerprint=f"m4-driver-{index}",
                    name=f"Week {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=(today - week).days, hours=2),
                    distance_m=volume * 1000,
                    duration_s=volume * 360,
                    avg_hr=145,
                    max_hr=170,
                )
            )
            session.add(
                PerformanceSnapshot(
                    snapshot_date=week,
                    computed_at=now - timedelta(days=(today - week).days),
                    model_version="m1.0",
                    fitness_anchor_s=fitness,
                    fitness_anchor_low_s=fitness - 40,
                    fitness_anchor_high_s=fitness + 40,
                    fitness_confidence="medium",
                    predictions=[
                        {
                            "distance_key": "10k",
                            "distance_m": 10000.0,
                            "planning_s": fitness,
                            "planning_low_s": fitness - 40,
                            "planning_high_s": fitness + 40,
                            "confidence": "medium",
                        }
                    ],
                )
            )
        session.commit()

        analysis = build_drivers(
            session,
            this_monday - timedelta(days=90),
            this_monday - timedelta(days=1),
            timedelta(0),
            threshold_pace=360.0,
            hr_reference=None,
        )
    finally:
        session.close()

    assert analysis.status == "ok"
    assert analysis.samples >= 6
    assert len(analysis.drivers) == 6
    assert "association_not_causation" in analysis.notes

    volume = next(item for item in analysis.drivers if item.key == "volume_m")
    assert volume.samples >= 6
    assert volume.correlation is not None
    assert volume.correlation > 0.5
    assert volume.direction == "positive"
    assert volume.strength in {"moderate", "strong"}
    assert volume.difference_pct is not None
    assert volume.difference_pct > 0
    assert "association_not_causation" in volume.reasons


def test_tracking_exposes_driver_analysis(client):
    _seed()
    client.get("/api/v1/performance")

    payload = client.get("/api/v1/tracking").json()
    drivers = payload["drivers"]
    assert drivers["status"] in {"ok", "insufficient"}
    assert len(drivers["drivers"]) == 6
    assert "association_not_causation" in drivers["notes"]
    assert all(item["confidence"] in {"low", "medium", "high"} for item in drivers["drivers"])
    assert "association_not_causation" in payload["notes"]
