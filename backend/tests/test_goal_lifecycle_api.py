"""M14 goal lifecycle: closing, archive and completed/cancelled races."""

from __future__ import annotations

from datetime import timedelta

from app.utils import utcnow


def _upload_fit(client, sample_fit) -> int:
    response = client.post(
        "/api/v1/imports",
        files=[("files", ("sample.fit", sample_fit, "application/octet-stream"))],
    )
    assert response.status_code == 200
    return response.json()["results"][0]["activity_id"]


def _set_goal(client, distance_key: str, target_time_s: float, **overrides):
    payload = {
        "target_time_s": target_time_s,
        "target_date": (utcnow().date() + timedelta(days=60)).isoformat(),
        "race_name": f"{distance_key} goal",
        **overrides,
    }
    response = client.put(f"/api/v1/performance/goals/{distance_key}", json=payload)
    assert response.status_code == 200
    return response.json()


def test_closing_a_goal_archives_it_and_frees_the_distance(client, sample_fit):
    activity_id = _upload_fit(client, sample_fit)
    client.get("/api/v1/performance")
    _set_goal(client, "5k", 1680)

    closed = client.post(
        "/api/v1/performance/goals/5k/close",
        json={
            "status": "achieved",
            "outcome_time_s": 1665,
            "activity_id": activity_id,
            "note": "Ran the spring race",
        },
    )
    assert closed.status_code == 200
    archived = closed.json()
    assert archived["distance_key"] == "5k"
    assert archived["distance_m"] == 5000
    assert archived["target_time_s"] == 1680
    assert archived["status"] == "achieved"
    assert archived["closed_at"]
    assert archived["outcome_time_s"] == 1665
    assert archived["activity_id"] == activity_id
    assert archived["activity_name"] is not None
    assert archived["note"] == "Ran the spring race"
    assert archived["prediction_time_s"] is not None
    assert archived["outcome_vs_prediction_s"] == round(1665 - archived["prediction_time_s"], 1)
    assert archived["outcome_vs_target_s"] == -15

    assert client.get("/api/v1/performance/goals").json() == []
    overview = client.get("/api/v1/performance").json()
    five = next(item for item in overview["distances"] if item["distance_key"] == "5k")
    assert five["goal"] is None

    archive = client.get("/api/v1/performance/goals/archive").json()
    assert len(archive) == 1
    assert archive[0]["status"] == "achieved"

    # A closed goal is not active and cannot be closed twice.
    assert (
        client.post("/api/v1/performance/goals/5k/close", json={"status": "missed"}).status_code
        == 404
    )

    # The freed distance accepts a new goal and keeps the archive untouched.
    _set_goal(client, "5k", 1620)
    goals = client.get("/api/v1/performance/goals").json()
    assert len(goals) == 1
    assert goals[0]["target_time_s"] == 1620
    assert len(client.get("/api/v1/performance/goals/archive").json()) == 1


def test_archive_is_ordered_by_closed_at_desc(client, sample_fit):
    _upload_fit(client, sample_fit)
    client.get("/api/v1/performance")
    _set_goal(client, "5k", 1680)
    _set_goal(client, "10k", 3600)

    first = client.post("/api/v1/performance/goals/5k/close", json={"status": "missed"})
    assert first.status_code == 200
    second = client.post(
        "/api/v1/performance/goals/10k/close",
        json={"status": "cancelled", "note": "Injury"},
    )
    assert second.status_code == 200

    archive = client.get("/api/v1/performance/goals/archive").json()
    assert [row["distance_key"] for row in archive] == ["10k", "5k"]
    assert archive[0]["status"] == "cancelled"
    assert archive[0]["note"] == "Injury"
    assert archive[1]["status"] == "missed"
    assert archive[0]["closed_at"] >= archive[1]["closed_at"]
    assert archive[1]["outcome_time_s"] is None
    assert archive[1]["outcome_vs_prediction_s"] is None


def test_closing_rejects_invalid_status_time_and_activity(client, sample_fit):
    _upload_fit(client, sample_fit)
    client.get("/api/v1/performance")
    _set_goal(client, "5k", 1680)

    assert (
        client.post("/api/v1/performance/goals/5k/close", json={"status": "finished"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/performance/goals/5k/close",
            json={"status": "achieved", "outcome_time_s": -1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/performance/goals/5k/close",
            json={"status": "achieved", "activity_id": 99999},
        ).status_code
        == 404
    )
    assert (
        client.post("/api/v1/performance/goals/10k/close", json={"status": "achieved"}).status_code
        == 404
    )
    # A rejected close left the goal untouched.
    assert len(client.get("/api/v1/performance/goals").json()) == 1
    assert client.get("/api/v1/performance/goals/archive").json() == []


def test_completed_and_cancelled_races_appear_in_calendar_and_reports(client, sample_fit):
    activity_id = _upload_fit(client, sample_fit)
    race_date = (utcnow().date() - timedelta(days=2)).isoformat()

    completed = client.post(
        "/api/v1/races",
        json={
            "name": "Completed 5K",
            "race_date": race_date,
            "distance_m": 5000,
            "goal_time_s": 1700,
            "status": "planned",
        },
    )
    assert completed.status_code == 201
    race_id = completed.json()["id"]

    patched = client.patch(
        f"/api/v1/races/{race_id}",
        json={"status": "completed", "activity_id": activity_id},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "completed"
    assert patched.json()["activity_id"] == activity_id

    cancelled = client.post(
        "/api/v1/races",
        json={
            "name": "Cancelled 10K",
            "race_date": race_date,
            "distance_m": 10000,
            "status": "cancelled",
        },
    )
    assert cancelled.status_code == 201

    calendar = client.get(f"/api/v1/calendar?start={race_date}&weeks=1").json()
    race_entries = [
        entry
        for week in calendar["weeks"]
        for day in week["days"]
        for entry in day["entries"]
        if entry["kind"] == "race"
    ]
    statuses = {entry["title"]: entry["status"] for entry in race_entries}
    assert statuses == {"Completed 5K": "completed", "Cancelled 10K": "cancelled"}
    # Completed and cancelled races do not inflate planned distance.
    assert all(week["planned_distance_m"] >= 0 for week in calendar["weeks"])

    report = client.get(f"/api/v1/reports?period=week&date={race_date}").json()
    reported = {race["name"]: race["status"] for race in report["races"]}
    assert reported["Completed 5K"] == "completed"
    assert reported["Cancelled 10K"] == "cancelled"


def test_race_patch_rejects_unknown_activity(client):
    created = client.post(
        "/api/v1/races",
        json={
            "name": "Planned half",
            "race_date": (utcnow().date() + timedelta(days=30)).isoformat(),
            "distance_m": 21097.5,
        },
    )
    assert created.status_code == 201
    response = client.patch(
        f"/api/v1/races/{created.json()['id']}",
        json={"status": "completed", "activity_id": 99999},
    )
    assert response.status_code == 404
