from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from app.config import get_settings
from app.db import get_session_factory
from app.models import IngestRun
from app.services.backup import database_path
from app.utils import utcnow


def _export(client) -> bytes:
    response = client.get("/api/v1/backups/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "run-backup-" in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"
    return response.content


def _manifest(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return json.loads(archive.read("manifest.json"))


def _rewrite(
    data: bytes,
    changes: dict[str, bytes],
    *,
    recalc: bool = False,
    manifest_update: dict | None = None,
) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries.update(changes)
    manifest = json.loads(entries["manifest.json"])
    if manifest_update:
        manifest.update(manifest_update)
    if recalc:
        for entry in manifest["files"]:
            payload = entries[entry["path"]]
            entry["size"] = len(payload)
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
    entries["manifest.json"] = json.dumps(manifest).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _validate(client, data: bytes):
    return client.post(
        "/api/v1/backups/validate",
        files={"file": ("backup.zip", data, "application/zip")},
    )


def test_export_contains_manifest_snapshot_raw_and_exports(client, sample_fit):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _export(client)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert "manifest.json" in names
        assert "run.db" in names
        assert any(name.startswith("raw/") for name in names)
        assert "exports/activities.csv" in names
        assert "exports/activities.json" in names
        assert "exports/goals.csv" in names
        assert "exports/races.json" in names
        assert "exports/actions.csv" in names
        assert "exports/external_metrics.json" in names
        assert not any(".env" in name for name in names)

        assert manifest["format"] == "run-backup"
        assert manifest["format_version"] == 1
        assert manifest["alembic_revision"]
        assert manifest["counts"]["activities"] == 1
        assert manifest["counts"]["raw_files"] == 1
        assert manifest["files"]
        for entry in manifest["files"]:
            payload = archive.read(entry["path"])
            assert entry["size"] == len(payload)
            assert entry["sha256"] == hashlib.sha256(payload).hexdigest()

    validation = _validate(client, data)
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["manifest"]["counts"]["activities"] == 1


def test_validate_rejects_altered_checksum(client, sample_fit):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _export(client)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        original = archive.read("exports/activities.csv")
    altered = original.replace(b"running", b"runninG", 1)
    assert len(altered) == len(original)
    data = _rewrite(data, {"exports/activities.csv": altered})
    response = _validate(client, data)
    assert response.status_code == 400
    body = response.json()
    assert body["valid"] is False
    assert any("Checksum mismatch" in error for error in body["errors"])


def test_validate_rejects_zip_slip(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../outside.txt", b"nope")
        archive.writestr("manifest.json", b"{}")
    response = _validate(client, buffer.getvalue())
    assert response.status_code == 400
    assert any("Unsafe" in error for error in response.json()["errors"])


def test_validate_rejects_symlink_entry(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("raw/link.fit")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"/etc/passwd")
        archive.writestr("manifest.json", b"{}")
    response = _validate(client, buffer.getvalue())
    assert response.status_code == 400
    assert any("Symbolic links" in error for error in response.json()["errors"])


def test_validate_rejects_excessive_uncompressed_size(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_restore_mb", 1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("raw/large.bin", b"\0" * (2 * 1024 * 1024))
        archive.writestr("manifest.json", b"{}")
    response = _validate(client, buffer.getvalue())
    assert response.status_code == 400
    errors = [error.lower() for error in response.json()["errors"]]
    assert any("limit" in error or "zip bomb" in error for error in errors)


def test_validate_rejects_zip_bomb_ratio(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_restore_mb", 64)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("raw/zeros.bin", b"\0" * (25 * 1024 * 1024))
        archive.writestr("manifest.json", b"{}")
    response = _validate(client, buffer.getvalue())
    assert response.status_code == 400
    assert any("zip bomb" in error.lower() for error in response.json()["errors"])


def test_validate_rejects_incompatible_revision(client, sample_fit):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _rewrite(_export(client), {}, manifest_update={"alembic_revision": "deadbeef"})
    response = _validate(client, data)
    assert response.status_code == 400
    assert any("not compatible" in error for error in response.json()["errors"])


def test_validate_rejects_corrupt_database(client, sample_fit):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _rewrite(_export(client), {"run.db": b"not a sqlite database"}, recalc=True)
    response = _validate(client, data)
    assert response.status_code == 400
    assert any("SQLite" in error or "integrity" in error for error in response.json()["errors"])


def test_restore_stages_pending_without_touching_live_data(client, sample_fit, sample_gpx):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _export(client)
    client.post(
        "/api/v1/imports",
        files=[("files", ("trail.gpx", sample_gpx, "application/gpx+xml"))],
    )
    assert client.get("/api/v1/activities").json()["total"] == 2

    response = client.post(
        "/api/v1/backups/restore",
        files={"file": ("backup.zip", data, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["staged"] is True
    assert body["pending"]["original_filename"] == "backup.zip"

    # The live database is untouched until the offline CLI runs.
    assert client.get("/api/v1/activities").json()["total"] == 2
    settings = get_settings()
    assert (settings.restore_pending_dir / "backup.zip").is_file()
    assert (settings.restore_pending_dir / "pending.json").is_file()

    status = client.get("/api/v1/backups/status").json()
    assert status["pending"]["manifest"]["counts"]["activities"] == 1
    assert status["pending"]["archive_size_bytes"] == len(data)
    assert status["max_restore_mb"] >= 1

    again = client.post(
        "/api/v1/backups/restore",
        files={"file": ("backup.zip", data, "application/zip")},
    )
    assert again.status_code == 409

    cancelled = client.delete("/api/v1/backups/pending")
    assert cancelled.status_code == 204
    assert client.get("/api/v1/backups/status").json()["pending"] is None
    assert not settings.restore_pending_dir.exists()
    assert client.delete("/api/v1/backups/pending").status_code == 404


def test_restore_rejects_while_sync_is_running(client, sample_fit):
    client.post(
        "/api/v1/imports",
        files=[("files", ("run.fit", sample_fit, "application/octet-stream"))],
    )
    data = _export(client)
    session = get_session_factory()()
    try:
        session.add(
            IngestRun(
                kind="garmin_sync",
                mode="incremental",
                status="running",
                started_at=utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/api/v1/backups/restore",
        files={"file": ("backup.zip", data, "application/zip")},
    )
    assert response.status_code == 409
    assert "running" in response.json()["detail"]
    assert not (get_settings().restore_pending_dir / "backup.zip").exists()


def test_status_reports_paths_and_revisions(client):
    status = client.get("/api/v1/backups/status")
    assert status.status_code == 200
    body = status.json()
    assert body["pending"] is None
    assert body["sync_running"] is False
    assert body["data_dir"] == str(get_settings().data_dir)
    assert body["head_revision"]
    assert body["database_revision"]
    assert Path(body["data_dir"]).is_dir()
    # Database exists even when no activities have been imported.
    assert database_path(get_settings()).parent.is_dir()
