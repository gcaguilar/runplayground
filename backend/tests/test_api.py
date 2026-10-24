from __future__ import annotations

from tests.helpers import make_matching_tcx


def _upload(client, name: str, data: bytes):
    return client.post(
        "/api/v1/imports",
        files=[("files", (name, data, "application/octet-stream"))],
    )


def test_import_fit_and_read_activity(client, sample_fit):
    response = _upload(client, "morning.fit", sample_fit)
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "imported"
    activity_id = result["activity_id"]

    listing = client.get("/api/v1/activities").json()
    assert listing["total"] == 1
    assert listing["items"][0]["sport"] == "running"
    assert listing["items"][0]["source_names"] == ["upload"]

    detail = client.get(f"/api/v1/activities/{activity_id}").json()
    assert detail["distance_m"] == 5000
    assert detail["has_streams"] is True
    assert detail["has_laps"] is True
    assert len(detail["laps"]) == 3
    assert detail["sources"][0]["raw_filename"] == "morning.fit"
    assert detail["device_name"] == "Forerunner 265"

    streams = client.get(f"/api/v1/activities/{activity_id}/streams?max_points=100").json()
    assert streams["total_points"] == 1801
    assert streams["downsampled"] is True
    assert len(streams["points"]) == 100
    assert streams["points"][0]["t"] == 0


def test_reupload_is_deduplicated(client, sample_fit):
    first = _upload(client, "run.fit", sample_fit).json()["results"][0]
    second = _upload(client, "run.fit", sample_fit).json()["results"][0]

    assert first["status"] == "imported"
    assert second["status"] == "duplicate"
    assert second["activity_id"] == first["activity_id"]
    assert client.get("/api/v1/activities").json()["total"] == 1
    assert client.get("/api/v1/system/status").json()["raw_file_count"] == 1


def test_cross_format_duplicate_is_merged_with_provenance(client, sample_fit):
    fit_result = _upload(client, "run.fit", sample_fit).json()["results"][0]
    tcx_result = _upload(client, "run.tcx", make_matching_tcx()).json()["results"][0]

    assert fit_result["status"] == "imported"
    assert tcx_result["status"] == "merged"
    assert tcx_result["activity_id"] == fit_result["activity_id"]
    assert client.get("/api/v1/activities").json()["total"] == 1

    detail = client.get(f"/api/v1/activities/{fit_result['activity_id']}").json()
    assert {source["source"] for source in detail["sources"]} == {"upload"}
    assert len(detail["sources"]) == 2
    assert len(detail["laps"]) == 3
    assert client.get("/api/v1/system/status").json()["raw_file_count"] == 2


def test_import_gpx(client, sample_gpx):
    result = _upload(client, "trail.gpx", sample_gpx).json()["results"][0]
    assert result["status"] == "imported"
    detail = client.get(f"/api/v1/activities/{result['activity_id']}").json()
    assert detail["sport"] == "running"
    assert detail["has_gps"] is True
    assert detail["name"] == "GPX test run"


def test_import_error_does_not_create_activity(client):
    response = _upload(client, "notes.txt", b"not an activity")
    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "error"
    assert client.get("/api/v1/activities").json()["total"] == 0
    imports = client.get("/api/v1/imports").json()
    assert imports[0]["status"] == "error"


def test_patch_marks_race_and_renames(client, sample_fit):
    activity_id = _upload(client, "race.fit", sample_fit).json()["results"][0]["activity_id"]
    response = client.patch(
        f"/api/v1/activities/{activity_id}",
        json={"name": "Carrera de primavera", "is_race": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Carrera de primavera"
    assert body["is_race"] is True


def test_weekly_summary_for_fixture_week(client, sample_fit):
    _upload(client, "run.fit", sample_fit)
    summary = client.get("/api/v1/summary/weekly?week_start=2026-05-25").json()

    assert summary["week_start"] == "2026-05-25"
    assert summary["totals"]["activities"] == 1
    assert summary["totals"]["distance_m"] == 5000
    assert summary["totals"]["active_days"] == 1
    assert summary["days"][5]["distance_m"] == 5000
    assert summary["by_sport"][0]["sport"] == "running"


def test_audit_reports_coverage_and_missing_key(client, sample_fit):
    _upload(client, "run.fit", sample_fit)
    report = client.get("/api/v1/audit").json()

    assert report["coverage"]["total_activities"] == 1
    assert report["coverage"]["pct_streams"] == 100
    assert report["coverage"]["pct_hr"] == 100
    assert report["garmin_configured"] is False
    codes = {finding["code"] for finding in report["findings"]}
    assert "no_garmin_key" in codes
    assert "no_activities" not in codes


def test_sync_requires_garmin_key(client):
    response = client.post("/api/v1/sync", json={"mode": "incremental"})
    assert response.status_code == 400
    status = client.get("/api/v1/sync/status").json()
    assert status["garmin_configured"] is False
    assert status["running"] is False


def test_unknown_activity(client):
    assert client.get("/api/v1/activities/9999").status_code == 404
