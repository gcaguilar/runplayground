from __future__ import annotations

from datetime import timedelta

from app.db import get_session_factory
from app.models import Activity, BestEffort
from app.utils import utcnow


def _seed_activity(kind: str = "run") -> int:
    session = get_session_factory()()
    now = utcnow()
    try:
        time_trial = Activity(
            fingerprint="m11-detail-10k",
            name="10K time trial",
            sport="running",
            start_time_utc=now - timedelta(days=20),
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
        for index in range(3):
            session.add(
                Activity(
                    fingerprint=f"m11-detail-fast-{index}",
                    name=f"Threshold {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=4 + index * 6),
                    distance_m=8000,
                    duration_s=2400,
                    avg_hr=168,
                    max_hr=184,
                )
            )
        slow = Activity(
            fingerprint="m11-detail-slow",
            name="Easy shakeout",
            sport="running",
            start_time_utc=now - timedelta(days=2),
            distance_m=8000,
            duration_s=4800,
            avg_hr=135,
            max_hr=150,
        )
        session.add(slow)
        if kind == "ride":
            session.add(
                Activity(
                    fingerprint="m11-detail-ride",
                    name="Bike",
                    sport="cycling",
                    start_time_utc=now - timedelta(days=3),
                    distance_m=30000,
                    duration_s=3600,
                )
            )
        session.commit()
        return slow.id
    finally:
        session.close()


def test_activity_detail_exposes_automatic_classification(client):
    slow_id = _seed_activity()

    detail = client.get(f"/api/v1/activities/{slow_id}").json()
    classification = detail["classification"]

    assert classification["key"] == "easy"
    assert classification["auto_key"] == "easy"
    assert classification["source"] == "auto"
    assert classification["overridden"] is False
    assert classification["mode"] == "auto"
    assert classification["threshold_pace_s_per_km"] == 300.0
    assert classification["hr_reference"] == 188


def test_patch_override_and_rpe_are_persisted_and_clearable(client):
    slow_id = _seed_activity()

    patched = client.patch(
        f"/api/v1/activities/{slow_id}",
        json={"intensity_override": "hard", "rpe": 8},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["intensity_override"] == "hard"
    assert body["rpe"] == 8
    assert body["classification"]["key"] == "hard"
    assert body["classification"]["auto_key"] == "easy"
    assert body["classification"]["source"] == "manual"
    assert body["classification"]["overridden"] is True

    # A patch that does not mention the override must preserve it.
    renamed = client.patch(
        f"/api/v1/activities/{slow_id}",
        json={"name": "Shakeout with strides"},
    ).json()
    assert renamed["intensity_override"] == "hard"
    assert renamed["rpe"] == 8
    assert renamed["classification"]["key"] == "hard"

    cleared = client.patch(
        f"/api/v1/activities/{slow_id}",
        json={"intensity_override": None, "rpe": None},
    ).json()
    assert cleared["intensity_override"] is None
    assert cleared["rpe"] is None
    assert cleared["classification"]["key"] == "easy"
    assert cleared["classification"]["source"] == "auto"

    assert client.get(f"/api/v1/activities/{slow_id}").json()["rpe"] is None


def test_patch_rejects_invalid_override_and_rpe(client):
    slow_id = _seed_activity()

    assert (
        client.patch(
            f"/api/v1/activities/{slow_id}",
            json={"intensity_override": "sprint"},
        ).status_code
        == 422
    )
    assert client.patch(f"/api/v1/activities/{slow_id}", json={"rpe": 0}).status_code == 422
    assert client.patch(f"/api/v1/activities/{slow_id}", json={"rpe": 11}).status_code == 422
    assert client.patch(f"/api/v1/activities/{slow_id}", json={"rpe": 10}).status_code == 200
    assert client.patch(f"/api/v1/activities/{slow_id}", json={"rpe": 1}).status_code == 200


def test_non_running_activity_has_no_classification(client):
    _seed_activity(kind="ride")

    listing = client.get("/api/v1/activities?sport=cycling").json()
    activity_id = listing["items"][0]["id"]
    detail = client.get(f"/api/v1/activities/{activity_id}").json()
    assert detail["classification"] is None


def test_override_changes_diagnostics_intensity_and_specificity(client):
    slow_id = _seed_activity()

    before = client.get("/api/v1/diagnostics?tz_offset_minutes=0").json()
    before_hard = next(item for item in before["dimensions"] if item["key"] == "specificity")[
        "metrics"
    ]["hard_sessions"]
    before_bucket = before["intensity"]["buckets"][2]["sessions"]

    client.patch(f"/api/v1/activities/{slow_id}", json={"intensity_override": "hard"})

    after = client.get("/api/v1/diagnostics?tz_offset_minutes=0").json()
    after_hard = next(item for item in after["dimensions"] if item["key"] == "specificity")[
        "metrics"
    ]["hard_sessions"]
    after_bucket = after["intensity"]["buckets"][2]["sessions"]

    assert after_bucket == before_bucket + 1
    assert after_hard == before_hard + 1
