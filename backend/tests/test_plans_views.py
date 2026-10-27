"""M12 calendar and adherence views with and without a registered plan."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, RaceGoal
from app.services.analysis import week_start
from app.utils import utcnow


def _seed_weeks(weeks: int = 9) -> None:
    session = get_session_factory()()
    now = utcnow()
    current = week_start(now.date())
    try:
        for offset in range(-weeks, 0):
            monday = current + timedelta(weeks=offset)
            for index, (day, distance, duration, hr) in enumerate(
                [
                    (0, 8000, 2880, 145),
                    (2, 6000, 1800, 176),
                    (5, 14000, 5040, 148),
                ]
            ):
                session.add(
                    Activity(
                        fingerprint=f"m12-week-{offset}-{index}",
                        name=f"Week {offset} run {index}",
                        sport="running",
                        start_time_utc=now
                        - timedelta(days=(now.date() - (monday + timedelta(days=day))).days),
                        distance_m=distance,
                        duration_s=duration,
                        avg_hr=hr,
                    )
                )
        for index in range(2):
            session.add(
                Activity(
                    fingerprint=f"m12-current-{index}",
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


def _create_plan(client, *, name: str, start: str, end: str) -> dict:
    response = client.post(
        "/api/v1/training-plans",
        json={"name": name, "start_date": start, "end_date": end},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add(client, plan_id: int, **payload) -> dict:
    response = client.post(f"/api/v1/training-plans/{plan_id}/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _current_monday():
    return week_start(utcnow().date())


def test_calendar_shows_registered_plan_inside_its_range(client):
    _seed_weeks()
    monday = _current_monday()
    plan = _create_plan(
        client,
        name="Registered block",
        start=monday.isoformat(),
        end=(monday + timedelta(days=13)).isoformat(),
    )
    _add(
        client,
        plan["id"],
        session_date=monday.isoformat(),
        type="easy",
        intensity="easy",
        distance_m=5000,
    )
    _add(
        client,
        plan["id"],
        session_date=(monday + timedelta(days=2)).isoformat(),
        type="long",
        intensity="easy",
        distance_m=12000,
    )
    _add(
        client,
        plan["id"],
        session_date=(monday + timedelta(days=4)).isoformat(),
        type="strength",
        intensity="moderate",
        duration_s=2700,
    )
    _add(
        client,
        plan["id"],
        session_date=(monday + timedelta(days=6)).isoformat(),
        type="rest",
        intensity="rest",
    )
    assert client.post(f"/api/v1/training-plans/{plan['id']}/activate").status_code == 200

    response = client.get(f"/api/v1/calendar?start={monday.isoformat()}&weeks=3")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_plan"] is not None
    assert payload["active_plan"]["id"] == plan["id"]
    assert payload["active_plan"]["name"] == "Registered block"

    first, second, third = payload["weeks"]
    first_entries = [entry for day in first["days"] for entry in day["entries"]]
    plan_entries = [entry for entry in first_entries if entry["kind"] == "plan"]
    assert {entry["title"] for entry in plan_entries} == {"easy", "long", "strength", "rest"}
    assert all(entry["session_id"] for entry in plan_entries)
    assert all(entry["plan_id"] == plan["id"] for entry in plan_entries)
    assert not [entry for entry in first_entries if entry["kind"] == "session"]
    assert not [
        entry for day in second["days"] for entry in day["entries"] if entry["kind"] == "session"
    ]
    # Only running sessions count towards planned distance: 5 km + 12 km.
    assert first["planned_distance_m"] == 17000.0
    # The second week is inside the plan range but has no registered sessions.
    assert second["planned_distance_m"] == 0.0

    # Outside the plan the M3 suggestion comes back.
    third_entries = [entry for day in third["days"] for entry in day["entries"]]
    assert [entry for entry in third_entries if entry["kind"] == "session"]
    assert third["planned_distance_m"] > 0


def test_calendar_without_plan_is_m3_compatible(client):
    _seed_weeks()
    monday = _current_monday()
    payload = client.get(f"/api/v1/calendar?start={monday.isoformat()}&weeks=2").json()
    assert payload["active_plan"] is None
    entries = [
        entry for week in payload["weeks"] for day in week["days"] for entry in day["entries"]
    ]
    assert {entry["kind"] for entry in entries} <= {"activity", "race", "session"}
    assert [entry for entry in entries if entry["kind"] == "session"]


def test_calendar_archived_plan_falls_back_to_suggested(client):
    _seed_weeks()
    monday = _current_monday()
    plan = _create_plan(
        client,
        name="Archived block",
        start=monday.isoformat(),
        end=(monday + timedelta(days=6)).isoformat(),
    )
    _add(
        client,
        plan["id"],
        session_date=monday.isoformat(),
        type="easy",
        intensity="easy",
        distance_m=5000,
    )
    client.post(f"/api/v1/training-plans/{plan['id']}/activate")
    client.post(f"/api/v1/training-plans/{plan['id']}/archive")

    payload = client.get(f"/api/v1/calendar?start={monday.isoformat()}&weeks=1").json()
    assert payload["active_plan"] is None
    entries = [entry for day in payload["weeks"][0]["days"] for entry in day["entries"]]
    assert not [entry for entry in entries if entry["kind"] == "plan"]
    assert [entry for entry in entries if entry["kind"] == "session"]


def test_adherence_mixes_registered_and_suggested_weeks(client):
    _seed_weeks()
    current = _current_monday()
    start = current - timedelta(weeks=4)
    end = current - timedelta(days=1)
    plan = _create_plan(
        client, name="Registered month", start=start.isoformat(), end=end.isoformat()
    )
    for week in range(4):
        monday = start + timedelta(weeks=week)
        _add(
            client,
            plan["id"],
            session_date=monday.isoformat(),
            type="easy",
            intensity="easy",
            distance_m=8000,
            status="completed",
        )
        _add(
            client,
            plan["id"],
            session_date=(monday + timedelta(days=2)).isoformat(),
            type="threshold",
            intensity="hard",
            distance_m=6000,
            status="skipped",
        )
        _add(
            client,
            plan["id"],
            session_date=(monday + timedelta(days=5)).isoformat(),
            type="long",
            intensity="easy",
            distance_m=14000,
        )
        _add(
            client,
            plan["id"],
            session_date=(monday + timedelta(days=6)).isoformat(),
            type="rest",
            intensity="rest",
        )
    client.post(f"/api/v1/training-plans/{plan['id']}/activate")

    payload = client.get("/api/v1/adherence?weeks=8").json()
    assert payload["basis"] == "mixed"
    assert payload["plan_id"] == plan["id"]
    assert payload["plan_name"] == "Registered month"
    assert payload["registered_weeks"] == 4
    assert payload["suggested_weeks"] == 4
    assert "registered_plan_used" in payload["notes"]
    assert "mixed_registered_and_suggested" in payload["notes"]
    assert "suggested_plan_not_registered" not in payload["notes"]

    registered = [item for item in payload["items"] if item["basis"] == "registered"]
    assert len(registered) == 4
    for item in registered:
        assert item["volume_low_m"] == 28000.0
        assert item["volume_high_m"] == 28000.0
        assert item["long_run_low_m"] == 14000.0
        assert item["quality_low"] == 1
        assert item["quality_high"] == 1
        assert item["rest_planned"] == 1
        assert item["sessions_planned"] == 3
        assert item["sessions_completed"] == 1
        assert item["sessions_skipped"] == 1
        assert item["sessions_missed"] == 1
        assert item["completion_rate"] is not None
        assert abs(item["completion_rate"] - 1 / 3) < 0.01
        outcomes = [entry["outcome"] for entry in item["session_items"]]
        assert sorted(outcomes) == ["completed", "missed", "skipped"]
        assert item["plan_id"] == plan["id"]

    current_item = payload["items"][-1]
    assert current_item["week_start"] == current.isoformat()
    assert current_item["basis"] == "suggested"
    assert current_item["status"] == "in_progress"
    assert current_item["score"] is None
    assert current_item["session_items"] == []

    summary = payload["summary"]
    assert summary["sessions_completed"] == 4
    assert summary["sessions_skipped"] == 4
    assert summary["sessions_missed"] == 4
    assert abs(summary["completion_rate"] - 4 / 12) < 0.01


def test_adherence_registered_basis_when_plan_covers_window(client):
    _seed_weeks()
    current = _current_monday()
    plan = _create_plan(
        client,
        name="Full window",
        start=(current - timedelta(weeks=7)).isoformat(),
        end=(current + timedelta(days=6)).isoformat(),
    )
    _add(
        client,
        plan["id"],
        session_date=current.isoformat(),
        type="easy",
        intensity="easy",
        distance_m=8000,
    )
    client.post(f"/api/v1/training-plans/{plan['id']}/activate")

    payload = client.get("/api/v1/adherence?weeks=8").json()
    assert payload["basis"] == "registered"
    assert payload["registered_weeks"] == 8
    assert payload["suggested_weeks"] == 0
    assert "registered_plan_used" in payload["notes"]
    assert "mixed_registered_and_suggested" not in payload["notes"]
    assert payload["items"][-1]["status"] == "in_progress"
    assert payload["items"][-1]["score"] is None


def test_adherence_ignores_archived_plan_and_keeps_m10_contract(client):
    _seed_weeks()
    current = _current_monday()
    plan = _create_plan(
        client,
        name="Archived",
        start=(current - timedelta(weeks=4)).isoformat(),
        end=(current + timedelta(days=6)).isoformat(),
    )
    _add(
        client,
        plan["id"],
        session_date=current.isoformat(),
        type="easy",
        intensity="easy",
        distance_m=8000,
    )
    client.post(f"/api/v1/training-plans/{plan['id']}/activate")
    client.post(f"/api/v1/training-plans/{plan['id']}/archive")

    payload = client.get("/api/v1/adherence?weeks=8").json()
    assert payload["basis"] == "suggested"
    assert payload["plan_id"] is None
    assert payload["plan_name"] is None
    assert payload["registered_weeks"] == 0
    assert payload["suggested_weeks"] == 8
    assert "suggested_plan_not_registered" in payload["notes"]
    assert "adherence_is_heuristic" in payload["notes"]
    assert set(payload["items"][0]["basis"] for _ in payload["items"][:1]) == {"suggested"}
    assert payload["items"][-1]["status"] == "in_progress"
    assert payload["summary"]["scored_weeks"] == 7
