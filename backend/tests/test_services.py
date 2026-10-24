from __future__ import annotations

import io
import zipfile
from datetime import datetime

import pytest

from app.auth import create_session, verify_session
from app.config import Settings
from app.parsers.fit import parse_fit
from app.services.garmin import GarminAuth, GarminAuthError
from app.services.garmin_mapping import merge_fit_with_garmin, parsed_from_garmin
from app.services.sync import extract_fit


def test_session_cookie_roundtrip_and_tampering():
    token = create_session("a" * 32, days=1)
    assert verify_session(token, "a" * 32)
    assert not verify_session(token, "b" * 32)
    assert not verify_session(token + "x", "a" * 32)
    assert not verify_session(None, "a" * 32)


def test_password_mode_requires_secret():
    with pytest.raises(ValueError):
        Settings(_env_file=None, auth_mode="password", app_password="secret", secret_key=None)
    settings = Settings(
        _env_file=None,
        auth_mode="password",
        app_password="secret",
        secret_key="0123456789abcdef",
    )
    assert settings.auth_mode == "password"


def test_garmin_auth_requires_key():
    settings = Settings(_env_file=None, garmin_personal_api_key=None)
    auth = GarminAuth(settings)
    with pytest.raises(GarminAuthError):
        auth.get_token()


def test_garmin_summary_mapping():
    summary = {
        "activityId": 123,
        "activityName": "Morning Run",
        "startTimeGMT": "2026-05-30 07:00:00",
        "activityType": {"typeKey": "trail_running"},
        "distance": 12345.0,
        "duration": 3600.0,
        "movingDuration": 3500.0,
        "elapsedDuration": 3700.0,
        "elevationGain": 250.0,
        "averageSpeed": 3.43,
        "maxSpeed": 5.1,
        "calories": 800,
        "averageHR": 150,
        "maxHR": 180,
        "averageRunningCadenceInStepsPerMinute": 176,
        "maxRunningCadenceInStepsPerMinute": 188,
        "aerobicTrainingEffect": 3.8,
        "activityTrainingLoad": 120,
        "description": "Trail day",
    }
    parsed = parsed_from_garmin(summary)
    assert parsed.sport == "running"
    assert parsed.sub_sport == "trail_running"
    assert parsed.start_time_utc == datetime(2026, 5, 30, 7, 0)
    assert parsed.avg_cadence_spm == 176
    assert parsed.name == "Morning Run"
    assert parsed.training_effect == 3.8
    assert parsed.training_load == 120


def test_merge_fit_keeps_streams_and_takes_garmin_name(sample_fit_data):
    fit = parse_fit(sample_fit_data)
    garmin = parsed_from_garmin(
        {
            "activityId": 1,
            "activityName": "Garmin name",
            "startTimeGMT": "2026-05-30 07:00:00",
            "activityType": {"typeKey": "running"},
            "distance": 5000,
            "duration": 1800,
        }
    )
    merged = merge_fit_with_garmin(fit, garmin)
    assert merged.name == "Garmin name"
    assert len(merged.samples) == 1801
    assert merged.distance_m == 5000


def test_extract_fit_from_zip(sample_fit_data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("activity.fit", sample_fit_data)
        archive.writestr("readme.txt", "hello")
    extracted = extract_fit(buffer.getvalue())
    assert extracted[8:12] == b".FIT"
    assert len(extracted) == len(sample_fit_data)


@pytest.fixture()
def sample_fit_data():
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "sample.fit").read_bytes()
