"""M12 registered training plan CRUD, validation and activity linking."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import get_session_factory
from app.models import Activity, PlannedRace, TrainingPlan
from app.utils import utcnow


def _plan_payload(**overrides) -> dict:
    today = utcnow().date()
    payload = {
        "name": "Autumn 10K block",
        "description": "Eight weeks with one quality session",
        "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": (today + timedelta(days=21)).isoformat(),
    }
    payload.update(overrides)
    return payload


def _create_plan(client, **overrides) -> dict:
    response = client.post("/api/v1/training-plans", json=_plan_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _session_payload(plan: dict, **overrides) -> dict:
    payload = {
        "session_date": plan["start_date"],
        "type": "easy",
        "intensity": "easy",
        "distance_m": 8000,
    }
    payload.update(overrides)
    return payload


def _add_session(client, plan: dict, **overrides) -> dict:
    response = client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions",
        json=_session_payload(plan, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _activity() -> int:
    session = get_session_factory()()
    try:
        activity = Activity(
            fingerprint="m12-linked-activity",
            name="Morning easy run",
            sport="running",
            start_time_utc=utcnow() - timedelta(days=1),
            distance_m=8100,
            duration_s=2900,
            avg_hr=140,
        )
        session.add(activity)
        session.commit()
        return activity.id
    finally:
        session.close()


def test_plan_crud_and_validation(client):
    plan = _create_plan(client)
    assert plan["is_active"] is False
    assert plan["version"] == 1
    assert plan["source"] == "manual"
    assert plan["sessions_total"] == 0

    listing = client.get("/api/v1/training-plans").json()
    assert [item["id"] for item in listing] == [plan["id"]]

    detail = client.get(f"/api/v1/training-plans/{plan['id']}")
    assert detail.status_code == 200
    assert detail.json()["sessions"] == []

    patched = client.patch(
        f"/api/v1/training-plans/{plan['id']}",
        json={"name": "Renamed block", "description": None},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed block"
    assert patched.json()["description"] is None
    assert patched.json()["version"] == 2

    bad_dates = client.patch(
        f"/api/v1/training-plans/{plan['id']}",
        json={"start_date": _plan_payload()["end_date"], "end_date": "2020-01-01"},
    )
    assert bad_dates.status_code == 422

    missing_goal = client.post("/api/v1/training-plans", json=_plan_payload(goal_race_id=999999))
    assert missing_goal.status_code == 422

    assert client.delete(f"/api/v1/training-plans/{plan['id']}").status_code == 204
    assert client.get(f"/api/v1/training-plans/{plan['id']}").status_code == 404


def test_plan_links_goal_race_and_returns_name(client):
    session = get_session_factory()()
    try:
        race = PlannedRace(
            name="City 10K",
            race_date=utcnow().date() + timedelta(days=28),
            distance_m=10000,
            goal_time_s=2940,
        )
        session.add(race)
        session.commit()
        race_id = race.id
    finally:
        session.close()

    plan = _create_plan(client, goal_race_id=race_id)
    assert plan["goal_race_id"] == race_id
    assert plan["goal_race_name"] == "City 10K"


def test_session_validation_rules(client):
    plan = _create_plan(client)
    url = f"/api/v1/training-plans/{plan['id']}/sessions"

    rest_with_target = client.post(
        url,
        json=_session_payload(plan, type="rest", intensity="rest", distance_m=5000),
    )
    assert rest_with_target.status_code == 422

    no_target = client.post(
        url,
        json=_session_payload(plan, distance_m=None),
    )
    assert no_target.status_code == 422

    wrong_intensity = client.post(
        url,
        json=_session_payload(plan, type="rest", intensity="easy", distance_m=None),
    )
    assert wrong_intensity.status_code == 422

    outside = client.post(
        url,
        json=_session_payload(plan, session_date="2030-01-01"),
    )
    assert outside.status_code == 422

    strength_with_duration = client.post(
        url,
        json=_session_payload(
            plan,
            type="strength",
            intensity="moderate",
            distance_m=None,
            duration_s=2700,
        ),
    )
    assert strength_with_duration.status_code == 201
    assert strength_with_duration.json()["type"] == "strength"


def test_activation_is_unique_and_requires_sessions(client):
    first = _create_plan(client, name="First")
    second = _create_plan(client, name="Second")
    _add_session(client, first)
    _add_session(client, second)

    empty = _create_plan(client, name="Empty")
    assert client.post(f"/api/v1/training-plans/{empty['id']}/activate").status_code == 409

    activated = client.post(f"/api/v1/training-plans/{first['id']}/activate")
    assert activated.status_code == 200
    assert activated.json() == {
        "plan_id": first["id"],
        "is_active": True,
        "replaced_plan_id": None,
    }

    replaced = client.post(f"/api/v1/training-plans/{second['id']}/activate")
    assert replaced.status_code == 200
    assert replaced.json()["replaced_plan_id"] == first["id"]

    listing = client.get("/api/v1/training-plans").json()
    active = [item for item in listing if item["is_active"]]
    assert [item["id"] for item in active] == [second["id"]]

    archived = client.post(f"/api/v1/training-plans/{second['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    assert archived.json()["archived_at"] is not None

    assert client.post(f"/api/v1/training-plans/{second['id']}/activate").status_code == 409
    visible = client.get("/api/v1/training-plans").json()
    assert second["id"] not in [item["id"] for item in visible]
    assert len(visible) == 2
    assert len(client.get("/api/v1/training-plans?include_archived=true").json()) == 3


def test_bulk_create_is_atomic(client):
    plan = _create_plan(client)
    url = f"/api/v1/training-plans/{plan['id']}/sessions/bulk"
    start = plan["start_date"]

    created = client.post(
        url,
        json={
            "sessions": [
                _session_payload(plan, session_date=start, type="easy"),
                _session_payload(
                    plan,
                    session_date=start,
                    type="rest",
                    intensity="rest",
                    distance_m=None,
                ),
            ]
        },
    )
    assert created.status_code == 201
    assert created.json()["created"] == 2

    detail = client.get(f"/api/v1/training-plans/{plan['id']}").json()
    assert detail["sessions_total"] == 1
    assert len(detail["sessions"]) == 2

    bad = client.post(
        url,
        json={
            "sessions": [
                _session_payload(plan, session_date=start, type="easy"),
                _session_payload(plan, session_date="2030-01-01", type="easy"),
            ]
        },
    )
    assert bad.status_code == 422
    detail = client.get(f"/api/v1/training-plans/{plan['id']}").json()
    assert len(detail["sessions"]) == 2

    too_many = client.post(
        url,
        json={"sessions": [_session_payload(plan, type="easy") for _ in range(401)]},
    )
    assert too_many.status_code == 422


def test_link_and_unlink_activity(client):
    plan = _create_plan(client)
    activity_id = _activity()
    first = _add_session(client, plan)
    second = _add_session(client, plan)
    skipped = _add_session(client, plan, status="skipped")

    linked = client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions/{first['id']}/activity",
        json={"activity_id": activity_id},
    )
    assert linked.status_code == 200
    assert linked.json()["status"] == "completed"
    assert linked.json()["activity_id"] == activity_id
    assert linked.json()["activity_name"] == "Morning easy run"

    duplicate = client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions/{second['id']}/activity",
        json={"activity_id": activity_id},
    )
    assert duplicate.status_code == 409

    skipped_link = client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions/{skipped['id']}/activity",
        json={"activity_id": activity_id},
    )
    assert skipped_link.status_code == 422

    missing = client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions/{second['id']}/activity",
        json={"activity_id": 999999},
    )
    assert missing.status_code == 404

    unlinked = client.delete(f"/api/v1/training-plans/{plan['id']}/sessions/{first['id']}/activity")
    assert unlinked.status_code == 200
    assert unlinked.json()["activity_id"] is None
    assert unlinked.json()["status"] == "planned"


def test_skipped_session_cannot_keep_activity(client):
    plan = _create_plan(client)
    activity_id = _activity()
    session = _add_session(client, plan)
    client.post(
        f"/api/v1/training-plans/{plan['id']}/sessions/{session['id']}/activity",
        json={"activity_id": activity_id},
    )
    response = client.patch(
        f"/api/v1/training-plans/{plan['id']}/sessions/{session['id']}",
        json={"status": "skipped"},
    )
    assert response.status_code == 422


def test_database_rejects_two_active_plans(client):
    today = utcnow().date()
    session = get_session_factory()()
    try:
        session.add_all(
            [
                TrainingPlan(
                    name="First active",
                    start_date=today,
                    end_date=today + timedelta(days=7),
                    is_active=True,
                ),
                TrainingPlan(
                    name="Second active",
                    start_date=today,
                    end_date=today + timedelta(days=7),
                    is_active=True,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_create_plan_from_suggested_materialises_sessions(client):
    today = utcnow().date()
    response = client.post(
        "/api/v1/training-plans/from-suggested",
        json={
            "name": "Suggested snapshot",
            "start_date": (today - timedelta(days=today.weekday())).isoformat(),
            "weeks": 4,
            "activate": True,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["source"] == "suggested"
    assert payload["is_active"] is True
    assert payload["sessions_total"] > 0
    assert len(payload["sessions"]) == 28
    assert payload["start_date"] == (today - timedelta(days=today.weekday())).isoformat()
    dates = [item["session_date"] for item in payload["sessions"]]
    assert min(dates) == payload["start_date"]
    assert max(dates) == payload["end_date"]
    assert any(item["type"] == "rest" for item in payload["sessions"])
