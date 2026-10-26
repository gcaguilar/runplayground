from __future__ import annotations

from datetime import date, timedelta

from app.db import get_session_factory
from app.models import Activity, BestEffort, ExternalMetric
from app.utils import utcnow


def _seed_analysis_data() -> None:
    session = get_session_factory()()
    now = utcnow()
    try:
        time_trial = Activity(
            fingerprint="analysis-10k",
            name="10K time trial",
            sport="running",
            start_time_utc=now - timedelta(days=14),
            distance_m=10000,
            duration_s=3000,
            avg_hr=170,
            max_hr=188,
            has_streams=True,
        )
        session.add(time_trial)
        session.flush()
        session.add(
            BestEffort(
                activity_id=time_trial.id,
                distance_m=10000,
                duration_s=3000,
                method="activity",
                is_full_activity=True,
                quality=0.95,
            )
        )

        for index in range(10):
            session.add(
                Activity(
                    fingerprint=f"analysis-easy-{index}",
                    name=f"Easy {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=1 + index * 4),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=145,
                    max_hr=168,
                )
            )

        session.add(
            Activity(
                fingerprint="analysis-long",
                name="Long run",
                sport="running",
                start_time_utc=now - timedelta(days=21),
                distance_m=16000,
                duration_s=5760,
                avg_hr=150,
                max_hr=170,
            )
        )
        session.add(
            Activity(
                fingerprint="analysis-hard",
                name="Threshold",
                sport="running",
                start_time_utc=now - timedelta(days=7),
                distance_m=8000,
                duration_s=2400,
                avg_hr=172,
                max_hr=186,
            )
        )
        for index, value in enumerate((52.0, 61.0, 68.0)):
            session.add(
                ExternalMetric(
                    source="garmin_export",
                    metric="training_readiness",
                    metric_date=date.today() - timedelta(days=index + 1),
                    value=value,
                    unit="score",
                )
            )
        session.commit()
    finally:
        session.close()


def test_diagnostics_empty_database(client):
    response = client.get("/api/v1/diagnostics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["headline"] == "insufficient"
    assert payload["score"] is None
    assert len(payload["dimensions"]) == 6
    assert payload["limiters"] == []
    assert payload["intensity"]["classified_sessions"] == 0
    assert len(payload["load"]["weekly"]) == 12
    assert payload["coverage"]["activities"] == 0
    assert "no_activities" in payload["warnings"]

    training = client.get("/api/v1/training").json()
    assert training["status"] == "insufficient"
    assert training["sessions"] == []
    assert training["focus"] == []
    assert "insufficient_data" in training["notes"]


def test_diagnostics_scores_six_dimensions(client):
    _seed_analysis_data()

    response = client.get("/api/v1/diagnostics?tz_offset_minutes=0")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] in {"ok", "strong"}
    assert payload["score"] is not None
    assert len(payload["dimensions"]) == 6
    assert {item["key"] for item in payload["dimensions"]} == {
        "volume",
        "consistency",
        "intensity",
        "load",
        "recovery",
        "specificity",
    }
    assert all(item["status"] != "unknown" for item in payload["dimensions"])

    intensity = payload["intensity"]
    assert len(intensity["buckets"]) == 3
    assert intensity["classified_sessions"] == 13
    assert intensity["buckets"][0]["share"] > 0.7
    assert intensity["buckets"][2]["share"] > 0.1

    load = payload["load"]
    assert len(load["weekly"]) == 12
    assert load["chronic_weekly"] > 0
    assert load["ratio"] is not None

    coverage = payload["coverage"]
    assert coverage["activities"] >= 10
    assert coverage["weeks_with_data"] >= 6
    assert coverage["has_anchor"] is True
    assert coverage["readiness_days"] == 3
    assert payload["reference"]["readiness_28d"] == 60.3
    assert "no_activities" not in payload["warnings"]
    assert "no_anchor" not in payload["warnings"]


def test_training_plan_maintenance_without_goal(client):
    _seed_analysis_data()

    response = client.get("/api/v1/training")
    assert response.status_code == 200
    plan = response.json()

    assert plan["status"] in {"ok", "strong"}
    assert plan["phase"] == "maintenance"
    assert plan["weeks_to_goal"] is None
    assert plan["goal"] is None
    assert len(plan["sessions"]) == 7
    assert {session["type"] for session in plan["sessions"]} >= {
        "easy",
        "long",
        "threshold",
        "rest",
    }
    assert plan["load_target"]["weekly_distance_low_m"] > 0
    assert (
        plan["load_target"]["weekly_distance_high_m"] > plan["load_target"]["weekly_distance_low_m"]
    )
    assert len(plan["focus"]) >= 1
    assert "goal_missing" in plan["notes"]


def test_training_plan_uses_goal_phase(client):
    _seed_analysis_data()
    target_date = (date.today() + timedelta(weeks=10)).isoformat()
    goal = client.put(
        "/api/v1/performance/goals/10k",
        json={
            "target_time_s": 3000,
            "target_date": target_date,
            "race_name": "Autumn 10K",
        },
    )
    assert goal.status_code == 200

    plan = client.get("/api/v1/training").json()
    assert plan["phase"] == "build"
    assert plan["phase_reason"] == "goal_build"
    assert plan["weeks_to_goal"] in {9, 10}
    assert plan["goal"]["race_name"] == "Autumn 10K"
    assert any(session["type"] == "race_pace" for session in plan["sessions"])

    diagnostics = client.get("/api/v1/diagnostics").json()
    assert diagnostics["goal"]["distance_m"] == 10000
    specificity = next(item for item in diagnostics["dimensions"] if item["key"] == "specificity")
    assert "race_specific" in specificity["reasons"]


def test_training_plan_tapers_near_goal(client):
    _seed_analysis_data()
    target_date = (date.today() + timedelta(days=6)).isoformat()
    client.put(
        "/api/v1/performance/goals/10k",
        json={"target_time_s": 3000, "target_date": target_date},
    )

    plan = client.get("/api/v1/training").json()
    assert plan["phase"] == "taper"
    assert plan["weeks_to_goal"] == 1
    types = [session["type"] for session in plan["sessions"]]
    assert "race_pace" in types
    assert "rest" in types
    assert "long" not in types
