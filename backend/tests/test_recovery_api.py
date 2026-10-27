"""M9 recovery context: tolerant import and context-only API."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta

from app.db import get_session_factory
from app.models import ExternalMetric
from app.utils import utcnow


def _seed(metric: str, values: list[tuple[int, float]], unit: str = "score") -> None:
    session = get_session_factory()()
    today = utcnow().date()
    try:
        for days_ago, value in values:
            session.add(
                ExternalMetric(
                    source="garmin_export",
                    metric=metric,
                    metric_date=today - timedelta(days=days_ago),
                    value=value,
                    unit=unit,
                    source_file="test.json",
                    source_key=metric,
                )
            )
        session.commit()
    finally:
        session.close()


def _export_zip() -> bytes:
    today = utcnow().date()
    day = (today - timedelta(days=1)).isoformat()
    older = (today - timedelta(days=29)).isoformat()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/sleepData.json",
            json.dumps(
                [
                    {"calendarDate": older, "sleepTimeSeconds": 25200},
                    {
                        "calendarDate": day,
                        "sleepTimeSeconds": 27000,
                        "sleepScore": {"overallScore": 82},
                    },
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/hrvData.json",
            json.dumps(
                [
                    {"calendarDate": older, "lastNightAvg": 48},
                    {"calendarDate": day, "lastNightAvg": 52},
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/healthStatusData.json",
            json.dumps(
                [
                    {
                        "calendarDate": day,
                        "restingHeartRate": 47,
                        "bodyBatteryMostRecentValue": 74,
                    }
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/bodyComposition.json",
            json.dumps(
                [
                    {"calendarDate": older, "weight": 71000},
                    {"calendarDate": day, "weightInKg": 70.4},
                ]
            ),
        )
    return buffer.getvalue()


def test_recovery_empty_database(client):
    response = client.get("/api/v1/recovery")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "insufficient"
    assert payload["days"] == 90
    assert payload["imported_at"] is None
    assert len(payload["metrics"]) == 6
    assert all(item["latest_value"] is None for item in payload["metrics"])
    assert "no_recovery_data" in payload["warnings"]
    assert "no_sleep_data" in payload["warnings"]
    assert "no_hrv_data" in payload["warnings"]
    assert "recovery_is_context_only" in payload["notes"]
    assert "not_medical_advice" in payload["notes"]


def test_recovery_is_partial_when_some_metrics_are_missing(client):
    _seed("sleep_duration", [(1, 27000), (29, 25200)], unit="s")

    response = client.get("/api/v1/recovery?days=90")
    payload = response.json()

    assert payload["status"] == "partial"
    sleep = next(item for item in payload["metrics"] if item["key"] == "sleep_duration")
    assert sleep["latest_value"] == 27000
    assert sleep["avg_7d"] == 27000
    assert sleep["avg_28d"] == 27000
    assert sleep["change_28d"] == 1800
    assert sleep["samples"] == 2
    assert sleep["coverage_days"] == 2
    assert "no_hrv_data" in payload["warnings"]
    assert "no_recovery_data" not in payload["warnings"]


def test_garmin_export_imports_recovery_metrics(client):
    response = client.post(
        "/api/v1/imports/garmin-export",
        files=[("file", ("export.zip", _export_zip(), "application/zip"))],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics_imported"] == 9

    recovery = client.get("/api/v1/recovery").json()
    assert recovery["status"] == "ok"
    assert recovery["imported_at"] is not None
    by_key = {item["key"]: item for item in recovery["metrics"]}

    assert by_key["sleep_duration"]["latest_value"] == 27000
    assert by_key["sleep_duration"]["change_28d"] == 1800
    assert by_key["sleep_score"]["latest_value"] == 82
    assert by_key["hrv"]["latest_value"] == 52
    assert by_key["resting_hr"]["latest_value"] == 47
    assert by_key["body_battery"]["latest_value"] == 74
    assert by_key["weight"]["latest_value"] == 70.4
    assert by_key["weight"]["change_28d"] == -0.6
    assert "no_recovery_data" not in recovery["warnings"]


def test_recovery_window_is_validated(client):
    assert client.get("/api/v1/recovery?days=6").status_code == 422
    assert client.get("/api/v1/recovery?days=731").status_code == 422
