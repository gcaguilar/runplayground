"""M3 API behaviour: progress, calendar, reports and planned races."""

from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, PerformanceSnapshot, RaceGoal
from app.utils import utcnow


def _seed_progress_data() -> dict[str, int]:
    session = get_session_factory()()
    now = utcnow()
    ids: dict[str, int] = {}
    try:
        ten_k = Activity(
            fingerprint="m3-10k-race",
            name="Autumn 10K",
            sport="running",
            start_time_utc=now - timedelta(days=14),
            distance_m=10000,
            duration_s=3000,
            avg_hr=176,
            max_hr=190,
            elevation_gain_m=40,
            is_race=True,
            has_streams=True,
            has_gps=True,
        )
        five_k = Activity(
            fingerprint="m3-5k-race",
            name="Park 5K",
            sport="running",
            start_time_utc=now - timedelta(days=21),
            distance_m=5000,
            duration_s=1500,
            avg_hr=180,
            max_hr=192,
            elevation_gain_m=15,
            is_race=True,
            has_gps=True,
        )
        session.add_all([ten_k, five_k])
        session.flush()
        ids["ten_k"] = ten_k.id
        ids["five_k"] = five_k.id

        for index in range(8):
            run = Activity(
                fingerprint=f"m3-easy-{index}",
                name=f"Easy {index}",
                sport="running",
                start_time_utc=now - timedelta(days=3 + index * 4),
                distance_m=8000,
                duration_s=2880,
                avg_hr=142,
                elevation_gain_m=10 if index % 2 == 0 else 0,
            )
            session.add(run)
            session.flush()
            ids[f"easy_{index}"] = run.id

        for index in range(2):
            session.add(
                PerformanceSnapshot(
                    snapshot_date=(now - timedelta(days=30 - index * 15)).date(),
                    computed_at=now - timedelta(days=30 - index * 15),
                    model_version="m1.0",
                    fitness_anchor_s=3050.0 - index * 25,
                    fitness_anchor_low_s=3000.0 - index * 25,
                    fitness_anchor_high_s=3100.0 - index * 25,
                    fitness_confidence="medium",
                )
            )
        session.add(
            RaceGoal(
                distance_m=10000,
                target_time_s=2940,
                target_date=(now + timedelta(days=70)).date(),
                race_name="City Marathon Weekend 10K",
            )
        )
        session.commit()
    finally:
        session.close()
    return ids


def _create_race(client, **overrides):
    payload = {
        "name": "Spring Half",
        "race_date": (utcnow().date() + timedelta(days=49)).isoformat(),
        "distance_m": 21097.5,
        "goal_time_s": 5700,
        "priority": "A",
        "location": "Riverside",
        "notes": "Flat course",
    }
    payload.update(overrides)
    return client.post("/api/v1/races", json=payload)


def test_progress_empty_database(client):
    response = client.get("/api/v1/progress")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["window_days"] == 180
    assert payload["totals"]["sessions"] == 0
    assert payload["previous"]["sessions"] == 0
    assert payload["delta"]["distance_pct"] is None
    assert payload["consistency"]["weeks_with_data"] == 0
    assert payload["consistency"]["current_streak_days"] == 0
    assert payload["best_efforts"] == []
    assert payload["goals"] == []
    assert payload["races"] == []
    assert "no_running_activities" in payload["warnings"]
    assert "no_goals" in payload["warnings"]
    assert "no_upcoming_races" in payload["warnings"]


def test_progress_overview_combines_measured_and_predicted_data(client):
    _seed_progress_data()

    response = client.get("/api/v1/progress?days=90")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["totals"]["sessions"] == 10
    assert payload["totals"]["distance_m"] > 0
    assert payload["totals"]["load"] > 0
    assert payload["totals"]["elevation_gain_m"] == 95
    assert len(payload["weeks"]) >= 13
    assert payload["consistency"]["weeks_with_data"] >= 5
    assert payload["consistency"]["longest_streak_days"] >= 1
    assert payload["consistency"]["best_week_m"] > 0

    effort_keys = {item["distance_key"] for item in payload["best_efforts"]}
    assert {"5k", "10k"}.issubset(effort_keys)
    five = next(item for item in payload["best_efforts"] if item["distance_key"] == "5k")
    assert five["time_s"] == 1500
    assert five["is_race"] is True

    assert len(payload["goals"]) == 1
    goal = payload["goals"][0]
    assert goal["distance_key"] == "10k"
    assert goal["target_time_s"] == 2940
    assert goal["current_time_s"] is not None
    assert goal["readiness_pct"] is not None
    assert goal["status"] in {"ahead", "close", "behind"}

    assert len(payload["fitness"]) >= 1
    highlight_keys = {item["key"] for item in payload["highlights"]}
    assert {"biggest_week", "longest_run", "most_elevation", "fastest_5k"}.issubset(highlight_keys)
    assert "no_fitness_history" not in payload["warnings"]


def test_calendar_merges_activities_races_and_suggested_sessions(client):
    _seed_progress_data()
    start = utcnow().date() - timedelta(days=7)
    race = _create_race(
        client,
        name="Calendar 10K",
        race_date=(start + timedelta(days=12)).isoformat(),
        distance_m=10000,
        goal_time_s=3000,
    )
    assert race.status_code == 201

    response = client.get(f"/api/v1/calendar?start={start.isoformat()}&weeks=4")
    assert response.status_code == 200
    payload = response.json()

    assert payload["start"] == (start - timedelta(days=start.weekday())).isoformat()
    assert payload["end"] > payload["start"]
    assert len(payload["weeks"]) == 4
    assert all(len(week["days"]) == 7 for week in payload["weeks"])
    assert payload["weeks"][0]["days"][0]["date"] == payload["start"]

    entries = [
        entry for week in payload["weeks"] for day in week["days"] for entry in day["entries"]
    ]
    kinds = {entry["kind"] for entry in entries}
    assert kinds == {"activity", "race", "session"}

    race_entries = [entry for entry in entries if entry["kind"] == "race"]
    assert race_entries[0]["race_id"] == race.json()["id"]
    assert race_entries[0]["is_race"] is True

    activity_entries = [entry for entry in entries if entry["kind"] == "activity"]
    assert activity_entries
    assert all(entry["activity_id"] for entry in activity_entries)

    session_entries = [entry for entry in entries if entry["kind"] == "session"]
    assert session_entries
    assert all(entry["status"] == "suggested" for entry in session_entries)
    assert any(entry["intensity"] == "hard" for entry in session_entries)

    week_actual = sum(week["actual_distance_m"] for week in payload["weeks"])
    day_actual = sum(day["actual_distance_m"] for week in payload["weeks"] for day in week["days"])
    assert week_actual == day_actual
    assert any(week["planned_distance_m"] > 0 for week in payload["weeks"])


def test_calendar_rejects_out_of_range_windows(client):
    assert client.get("/api/v1/calendar?weeks=0").status_code == 422
    assert client.get("/api/v1/calendar?weeks=13").status_code == 422


def test_weekly_and_monthly_reports(client):
    _seed_progress_data()
    today = utcnow().date()
    anchor = today - timedelta(days=3)

    week = client.get(f"/api/v1/reports?period=week&date={anchor.isoformat()}")
    assert week.status_code == 200
    payload = week.json()

    assert payload["period"] == "week"
    assert payload["start"] == (anchor - timedelta(days=anchor.weekday())).isoformat()
    assert len(payload["days"]) == 7
    assert len(payload["weeks"]) >= 1
    assert payload["totals"]["sessions"] > 0
    assert payload["by_sport"][0]["sport"] == "running"
    assert payload["load"]["status"] in {
        "unknown",
        "strong",
        "ok",
        "watch",
        "risk",
    }
    assert "load_is_estimated" in payload["notes"]
    assert "not_medical_advice" in payload["notes"]
    assert "narrative_is_derived" in payload["notes"]
    narrative = payload["narrative"]
    assert narrative["key"] in {
        "fitness_up",
        "fitness_down",
        "volume_up",
        "volume_down",
        "stable",
        "insufficient",
    }
    assert narrative["tone"] in {"positive", "neutral", "warning", "danger"}
    assert narrative["action"]
    assert narrative["confidence"] in {"low", "medium", "high"}
    assert narrative["reasons"]
    assert payload["goals"]

    month = client.get(f"/api/v1/reports?period=month&date={today.isoformat()}")
    assert month.status_code == 200
    payload = month.json()
    assert payload["period"] == "month"
    assert payload["start"] == today.replace(day=1).isoformat()
    assert 28 <= len(payload["days"]) <= 31
    assert payload["label"] == f"{today.year}-{today.month:02d}"
    assert payload["totals"]["sessions"] > 0

    assert client.get("/api/v1/reports?period=year").status_code == 422


def test_race_crud_and_validation(client):
    today = utcnow().date()
    assert client.get("/api/v1/races").json() == []

    created = _create_race(client)
    assert created.status_code == 201
    race = created.json()
    race_id = race["id"]
    assert race["name"] == "Spring Half"
    assert race["priority"] == "A"
    assert race["status"] == "planned"
    assert race["days_to_race"] == 49
    assert race["weeks_to_race"] == 7
    assert race["phase"] in {"base", "build", "peak", "taper"}
    assert race["target_pace_s_per_km"] is not None
    assert race["readiness"] in {"ahead", "on_track", "close", "behind", "unknown"}
    assert race["weekly_distance_low_m"] is not None
    assert race["long_run_low_m"] is not None

    listed = client.get("/api/v1/races")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [race_id]

    second = _create_race(
        client,
        name="Trail 21K",
        race_date=(today + timedelta(days=10)).isoformat(),
        distance_m=21000,
        goal_time_s=None,
        priority="B",
    )
    assert second.status_code == 201
    assert second.json()["readiness"] == "unknown"

    patched = client.patch(
        f"/api/v1/races/{race_id}",
        json={"goal_time_s": 5400, "status": "completed", "priority": "B"},
    )
    assert patched.status_code == 200
    assert patched.json()["goal_time_s"] == 5400
    assert patched.json()["status"] == "completed"
    assert patched.json()["priority"] == "B"

    assert client.delete(f"/api/v1/races/{race_id}").status_code == 204
    assert client.delete(f"/api/v1/races/{race_id}").status_code == 404
    assert client.patch("/api/v1/races/99999", json={"name": "Nope"}).status_code == 404

    bad_priority = _create_race(client, priority="Z")
    assert bad_priority.status_code == 422
    bad_distance = _create_race(client, distance_m=0)
    assert bad_distance.status_code == 422
    missing_activity = _create_race(client, activity_id=99999)
    assert missing_activity.status_code == 404


def test_race_can_link_a_completed_activity(client):
    ids = _seed_progress_data()

    created = _create_race(
        client,
        name="Completed 10K",
        race_date=(utcnow().date() - timedelta(days=14)).isoformat(),
        distance_m=10000,
        status="completed",
        activity_id=ids["ten_k"],
    )
    assert created.status_code == 201
    assert created.json()["activity_id"] == ids["ten_k"]

    calendar = client.get(
        f"/api/v1/calendar?start={(utcnow().date() - timedelta(days=21)).isoformat()}&weeks=4"
    ).json()
    entries = [
        entry
        for week in calendar["weeks"]
        for day in week["days"]
        for entry in day["entries"]
        if entry["kind"] == "race"
    ]
    assert entries[0]["race_id"] == created.json()["id"]
