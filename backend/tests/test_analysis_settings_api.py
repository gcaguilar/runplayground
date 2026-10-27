from __future__ import annotations

from datetime import date, timedelta

from app.db import get_session_factory
from app.models import Activity, BestEffort, ExternalMetric
from app.utils import utcnow


def _seed_anchor_and_runs() -> None:
    session = get_session_factory()()
    now = utcnow()
    try:
        time_trial = Activity(
            fingerprint="m11-10k",
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
        for index in range(6):
            session.add(
                Activity(
                    fingerprint=f"m11-run-{index}",
                    name=f"Steady {index}",
                    sport="running",
                    start_time_utc=now - timedelta(days=2 + index * 5),
                    distance_m=8000,
                    duration_s=2400,
                    avg_hr=168,
                    max_hr=184,
                )
            )
        session.add(
            ExternalMetric(
                source="garmin_export",
                metric="resting_hr",
                metric_date=date.today() - timedelta(days=1),
                value=48,
                unit="bpm",
            )
        )
        session.commit()
    finally:
        session.close()


def test_empty_settings_are_explicit_about_missing_data(client):
    response = client.get("/api/v1/analysis/settings")
    assert response.status_code == 200
    payload = response.json()

    assert payload["observed"]["max_hr"] is None
    assert payload["observed"]["threshold_hr"] is None
    assert payload["observed"]["threshold_pace_s_per_km"] is None
    assert payload["manual"] == {
        "max_hr": None,
        "resting_hr": None,
        "threshold_hr": None,
        "threshold_pace_s_per_km": None,
        "classification_mode": None,
    }
    assert payload["effective"]["classification_mode"] == "auto"
    assert payload["sources"]["max_hr"] == "missing"
    assert payload["sources"]["threshold_pace_s_per_km"] == "missing"
    assert payload["warnings"]
    assert payload["updated_at"] is None


def test_observed_values_come_from_data_and_threshold_hr_is_derived(client):
    _seed_anchor_and_runs()

    payload = client.get("/api/v1/analysis/settings").json()

    assert payload["observed"]["threshold_pace_s_per_km"] == 300.0
    assert payload["observed"]["max_hr"] == 188
    assert payload["observed"]["resting_hr"] == 48
    assert payload["observed"]["threshold_hr"] is None
    assert payload["sources"]["threshold_pace_s_per_km"] == "observed"
    assert payload["sources"]["max_hr"] == "observed"
    assert payload["sources"]["resting_hr"] == "observed"
    assert payload["sources"]["threshold_hr"] == "missing"
    assert payload["sources"]["classification_mode"] == "derived"
    assert payload["effective"]["threshold_hr"] is None
    assert "no_threshold_hr" in payload["warnings"]


def test_settings_put_persists_and_can_be_cleared(client):
    _seed_anchor_and_runs()

    response = client.put(
        "/api/v1/analysis/settings",
        json={
            "max_hr": 190,
            "resting_hr": 46,
            "threshold_hr": 172,
            "threshold_pace_s_per_km": 245,
            "classification_mode": "pace",
        },
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["effective"] == {
        "max_hr": 190,
        "resting_hr": 46,
        "threshold_hr": 172,
        "threshold_pace_s_per_km": 245.0,
        "classification_mode": "pace",
    }
    assert set(saved["sources"].values()) == {"manual"}
    assert saved["updated_at"] is not None

    reread = client.get("/api/v1/analysis/settings").json()
    assert reread["manual"] == saved["manual"]
    assert reread["effective"] == saved["effective"]

    cleared = client.put(
        "/api/v1/analysis/settings",
        json={
            "max_hr": None,
            "resting_hr": None,
            "threshold_hr": None,
            "threshold_pace_s_per_km": None,
            "classification_mode": None,
        },
    )
    assert cleared.status_code == 200
    payload = cleared.json()
    assert payload["manual"]["max_hr"] is None
    assert payload["effective"]["max_hr"] == 188
    assert payload["effective"]["threshold_pace_s_per_km"] == 300.0
    assert payload["effective"]["classification_mode"] == "auto"


def test_settings_reject_out_of_range_and_incoherent_values(client):
    _seed_anchor_and_runs()

    assert client.put("/api/v1/analysis/settings", json={"max_hr": 99}).status_code == 422
    assert client.put("/api/v1/analysis/settings", json={"max_hr": 231}).status_code == 422
    assert (
        client.put("/api/v1/analysis/settings", json={"threshold_pace_s_per_km": 119}).status_code
        == 422
    )
    assert client.put("/api/v1/analysis/settings", json={"resting_hr": 121}).status_code == 422
    assert (
        client.put(
            "/api/v1/analysis/settings",
            json={"max_hr": 190, "threshold_hr": 200},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/analysis/settings",
            json={"resting_hr": 100, "threshold_hr": 100},
        ).status_code
        == 422
    )
    # Coherence is also checked against the observed max HR.
    response = client.put("/api/v1/analysis/settings", json={"threshold_hr": 195})
    assert response.status_code == 422
    assert "threshold_hr" in response.json()["detail"]


def test_manual_thresholds_change_diagnostics_and_plan_not_the_anchor(client):
    _seed_anchor_and_runs()

    before_diagnostics = client.get("/api/v1/diagnostics?tz_offset_minutes=0").json()
    before_training = client.get("/api/v1/training?tz_offset_minutes=0").json()
    before_intensity = before_diagnostics["intensity"]
    assert before_diagnostics["coverage"]["anchor_pace_s_per_km"] == 300.0
    assert before_intensity["buckets"][2]["sessions"] > 0

    saved = client.put(
        "/api/v1/analysis/settings",
        json={"threshold_pace_s_per_km": 240, "classification_mode": "pace"},
    )
    assert saved.status_code == 200

    after_diagnostics = client.get("/api/v1/diagnostics?tz_offset_minutes=0").json()
    after_training = client.get("/api/v1/training?tz_offset_minutes=0").json()

    # The observed anchor stays untouched: predictions keep their input.
    assert after_diagnostics["coverage"]["anchor_pace_s_per_km"] == 300.0
    assert after_diagnostics["intensity"]["buckets"][2]["sessions"] == 0
    assert after_diagnostics["intensity"]["buckets"][0]["sessions"] >= 6

    before_duration = sum(
        (session["duration_low_s"] or 0.0) + (session["duration_high_s"] or 0.0)
        for session in before_training["sessions"]
    )
    after_duration = sum(
        (session["duration_low_s"] or 0.0) + (session["duration_high_s"] or 0.0)
        for session in after_training["sessions"]
    )
    assert after_duration < before_duration
    assert "manual_thresholds_applied" in after_training["notes"]
    assert "classification_mode_pace" in after_training["notes"]

    anchor = client.get("/api/v1/performance").json()["fitness_anchor"]
    assert anchor["pace_s_per_km"] == 300.0
