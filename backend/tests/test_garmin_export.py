from __future__ import annotations

import io
import json
import zipfile

import pytest


def _export_zip(sample_fit: bytes, *, invalid_json: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "DI_CONNECT/DI-Connect-Metrics/2026_vo2Max.json",
            json.dumps(
                [
                    {"calendarDate": "2026-09-01", "vo2Max": 52.4},
                    {"calendarDate": "2026-09-02", "vo2MaxPreciseValue": 52.7},
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Fitness/2026_racePredictions.json",
            json.dumps(
                [
                    {
                        "calendarDate": "2026-09-01",
                        "racePrediction": {
                            "5K": 1290,
                            "10K": 2700,
                            "halfMarathon": 5940,
                            "marathon": 12600,
                        },
                    }
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/2026_trainingReadiness.json",
            json.dumps([{"calendarDate": "2026-09-03", "score": 72}]),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Wellness/2026_trainingStatus.json",
            json.dumps(
                [
                    {
                        "calendarDate": "2026-09-03",
                        "acuteTrainingLoad": 300,
                        "chronicTrainingLoad": 250.5,
                    }
                ]
            ),
        )
        archive.writestr(
            "DI_CONNECT/DI-Connect-Fitness/123456.fit",
            sample_fit,
        )
        if invalid_json:
            archive.writestr("DI_CONNECT/broken.json", "{not json")
    return buffer.getvalue()


def _post_export(client, data: bytes):
    return client.post(
        "/api/v1/imports/garmin-export",
        files=[("file", ("garmin-export.zip", data, "application/zip"))],
    )


def test_garmin_export_imports_metrics_and_fit_activities(client, sample_fit):
    response = _post_export(client, _export_zip(sample_fit))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["files_scanned"] == 5
    assert payload["metrics_imported"] == 9
    assert payload["activities_imported"] == 1
    assert payload["warnings"] == []

    overview = client.get("/api/v1/performance").json()
    reference = overview["garmin"]
    assert reference["vo2max"]["value"] == 52.7
    assert len(reference["vo2max_series"]) == 2
    assert reference["readiness"]["value"] == 72
    assert reference["acute_training_load"]["value"] == 300
    assert reference["chronic_training_load"]["value"] == 250.5
    assert [item["distance_m"] for item in reference["race_predictions"]] == [
        5000.0,
        10000.0,
        21097.5,
        42195.0,
    ]
    assert reference["race_predictions"][0]["time_s"] == 1290
    assert "no_garmin_export" not in overview["warnings"]

    imports = client.get("/api/v1/imports").json()
    assert imports[0]["kind"] == "garmin_export"
    assert imports[0]["status"] == "success"


def test_garmin_export_is_idempotent(client, sample_fit):
    data = _export_zip(sample_fit)
    assert _post_export(client, data).status_code == 200
    second = _post_export(client, data)
    assert second.status_code == 200
    payload = second.json()
    assert payload["metrics_imported"] == 0
    assert payload["metrics_skipped"] == 9
    assert payload["activities_imported"] == 0
    assert payload["activities_skipped"] == 1


def test_garmin_export_reports_broken_documents(client, sample_fit):
    response = _post_export(client, _export_zip(sample_fit, invalid_json=True))
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics_imported"] == 9
    assert any(warning.startswith("invalid_json:") for warning in payload["warnings"])


def test_garmin_export_rejects_non_zip(client):
    response = client.post(
        "/api/v1/imports/garmin-export",
        files=[("file", ("export.zip", b"not a zip", "application/zip"))],
    )
    assert response.status_code == 400
    response = client.post(
        "/api/v1/imports/garmin-export",
        files=[("file", ("export.json", b"{}", "application/json"))],
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("5K", 5000.0),
        ("time10k", 10000.0),
        ("halfMarathon", 21097.5),
        ("predictionMarathon", 42195.0),
        ("800m", None),
    ],
)
def test_distance_key_detection(key, expected):
    from app.services.garmin_export import _distance_for_key

    assert _distance_for_key(key) == expected
