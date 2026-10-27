"""M10 suggested-plan adherence API."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, RaceGoal
from app.services.analysis import week_start
from app.utils import utcnow


def _seed() -> None:
    session = get_session_factory()()
    now = utcnow()
    today = now.date()
    current = week_start(today)
    try:
        for offset in range(-8, 0):
            monday = current + timedelta(weeks=offset)
            for index, (day, distance, duration) in enumerate(
                [
                    (0, 8000, 2880),
                    (2, 6000, 1800),
                    (4, 8000, 2880),
                    (5, 14000, 5040),
                ]
            ):
                session.add(
                    Activity(
                        fingerprint=f"m10-{offset}-{index}",
                        name=f"Week {offset} run {index}",
                        sport="running",
                        start_time_utc=now
                        - timedelta(days=(today - (monday + timedelta(days=day))).days),
                        distance_m=distance,
                        duration_s=duration,
                        avg_hr=150 if index != 1 else 178,
                        elevation_gain_m=10,
                    )
                )
        # A partial current week: it must be marked in progress and excluded.
        for index in range(2):
            session.add(
                Activity(
                    fingerprint=f"m10-current-{index}",
                    name=f"Current {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=index),
                    distance_m=8000,
                    duration_s=2880,
                    avg_hr=145,
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


def test_adherence_empty_database(client):
    response = client.get("/api/v1/adherence?weeks=8")
    assert response.status_code == 200
    payload = response.json()

    assert payload["weeks"] == 8
    assert payload["status"] == "insufficient"
    assert len(payload["items"]) == 8
    assert payload["summary"]["scored_weeks"] == 0
    assert payload["summary"]["average_score"] is None
    assert payload["summary"]["current_score"] is None
    assert payload["items"][-1]["status"] == "in_progress"
    assert "no_activities" in payload["warnings"]
    assert "no_completed_weeks" in payload["warnings"]
    assert "no_goal" in payload["warnings"]
    assert "current_week_in_progress" in payload["warnings"]
    assert "suggested_plan_not_registered" in payload["notes"]
    assert "adherence_is_heuristic" in payload["notes"]


def test_adherence_compares_completed_weeks_and_excludes_current(client):
    _seed()

    response = client.get("/api/v1/adherence?weeks=8")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] in {"ok", "partial"}
    assert len(payload["items"]) == 8
    current = payload["items"][-1]
    assert current["status"] == "in_progress"
    assert current["score"] is None
    assert "week_in_progress" in current["reasons"]

    completed = [item for item in payload["items"] if item["status"] != "in_progress"]
    assert len(completed) == 7
    assert all(item["score"] is not None for item in completed)
    assert all(0 <= item["score"] <= 100 for item in completed)
    assert any(item["volume_status"] == "within" for item in completed)
    assert any(item["long_run_status"] == "over" for item in completed)

    summary = payload["summary"]
    assert summary["weeks"] == 8
    assert summary["scored_weeks"] == 7
    assert summary["average_score"] is not None
    assert summary["current_score"] is None
    assert summary["trend"] in {"improving", "stable", "worsening", "unknown"}
    assert summary["volume_ratio"] is not None
    assert summary["long_run_ratio"] is not None
    assert "current_week_in_progress" in payload["warnings"]
    assert "no_goal" not in payload["warnings"]


def test_adherence_window_is_validated(client):
    assert client.get("/api/v1/adherence?weeks=4").status_code == 200
    assert client.get("/api/v1/adherence?weeks=12").status_code == 200
    assert client.get("/api/v1/adherence?weeks=5").status_code == 422
    assert client.get("/api/v1/adherence?weeks=0").status_code == 422
