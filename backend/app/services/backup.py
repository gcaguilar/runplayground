"""Portable backup export and safe offline restore.

The export is a ZIP archive built around a consistent SQLite snapshot (made
with the sqlite3 backup API, so committed WAL pages are included), the raw
files referenced by the database and plain CSV/JSON exports of the user-facing
tables. The manifest records the format, versions, row counts and a SHA-256
checksum for every entry.

Restore never touches live data from an HTTP request: the archive is validated,
copied to ``DATA_DIR/restore/pending`` and applied by
``python -m app.cli apply-restore`` before Alembic runs at startup. Only that
offline step replaces the database and raw directory, keeping a
``run.db.pre-restore-<timestamp>`` snapshot first.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base
from app.models import (
    Activity,
    ActivityLap,
    ExternalMetric,
    PlannedRace,
    RaceGoal,
    RawFile,
    StreamSample,
    TrackedAction,
)
from app.utils import utcnow

logger = logging.getLogger(__name__)

BACKUP_FORMAT = "run-backup"
BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "run.db"
PENDING_ARCHIVE_NAME = "backup.zip"
PENDING_METADATA_NAME = "pending.json"
MAX_ENTRIES = 20_000
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
COMPRESSION_RATIO_LIMIT = 100
COMPRESSION_RATIO_MIN_BYTES = 20 * 1024 * 1024
HASH_CHUNK = 1024 * 1024

EXPORT_MODELS: tuple[tuple[str, type[Any]], ...] = (
    ("activities", Activity),
    ("goals", RaceGoal),
    ("races", PlannedRace),
    ("actions", TrackedAction),
    ("external_metrics", ExternalMetric),
)


class BackupError(Exception):
    """A backup/restore operation cannot continue."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "backup_error",
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []


@dataclass
class BackupResult:
    path: Path
    filename: str
    size_bytes: int
    created_at: datetime


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    archive_size_bytes: int = 0
    uncompressed_size_bytes: int = 0
    file_count: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest": manifest_summary(self.manifest),
            "archive_size_bytes": self.archive_size_bytes,
            "uncompressed_size_bytes": self.uncompressed_size_bytes,
            "file_count": self.file_count,
        }


@dataclass
class PendingRestore:
    directory: Path
    archive_path: Path
    staged_at: datetime
    original_filename: str
    archive_size_bytes: int
    archive_sha256: str
    manifest: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "staged_at": self.staged_at,
            "original_filename": self.original_filename,
            "archive_size_bytes": self.archive_size_bytes,
            "archive_sha256": self.archive_sha256,
            "manifest": manifest_summary(self.manifest),
            "warnings": self.warnings,
        }


@dataclass
class ApplyRestoreResult:
    applied: bool
    message: str
    applied_at: datetime | None = None
    pre_restore_database: Path | None = None
    manifest: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Public operations


def create_backup(settings: Settings, db: Session) -> BackupResult:
    """Build a consistent ZIP backup and return the temporary file holding it."""
    settings.ensure_dirs()
    db_path = database_path(settings)
    if not db_path.is_file():
        raise BackupError(f"SQLite database not found at {db_path}")

    max_bytes = max(settings.max_backup_mb, 1) * 1024 * 1024
    work_dir = Path(tempfile.mkdtemp(prefix="run-backup-", dir=settings.tmp_dir))
    archive_path = work_dir / "backup.zip"
    try:
        snapshot = work_dir / DATABASE_NAME
        _snapshot_sqlite(db_path, snapshot)
        if snapshot.stat().st_size > max_bytes:
            raise BackupError(
                f"Backup exceeds the {settings.max_backup_mb} MB limit",
                code="backup_too_large",
            )

        files: list[dict[str, Any]] = []
        sources: dict[str, Path] = {DATABASE_NAME: snapshot}
        warnings: list[str] = []
        total_bytes = 0

        def add_file(source: Path, archive_name: str, kind: str) -> None:
            nonlocal total_bytes
            size = source.stat().st_size
            total_bytes += size
            if total_bytes > max_bytes:
                raise BackupError(
                    f"Backup exceeds the {settings.max_backup_mb} MB limit",
                    code="backup_too_large",
                )
            sources[archive_name] = source
            files.append(
                {
                    "path": archive_name,
                    "kind": kind,
                    "size": size,
                    "sha256": sha256_file(source),
                }
            )

        add_file(snapshot, DATABASE_NAME, "database")

        raw_entries = _backup_raw_files(settings, db, warnings)
        for source, archive_name in raw_entries:
            add_file(source, archive_name, "raw")

        export_counts: dict[str, int] = {}
        for name, model in EXPORT_MODELS:
            rows = _table_rows(db, model)
            export_counts[name] = len(rows)
            csv_bytes = _rows_to_csv(model, rows)
            json_bytes = _rows_to_json(rows)
            csv_path = _add_bytes(work_dir, files, f"exports/{name}.csv", "export", csv_bytes)
            json_path = _add_bytes(work_dir, files, f"exports/{name}.json", "export", json_bytes)
            sources[f"exports/{name}.csv"] = csv_path
            sources[f"exports/{name}.json"] = json_path
            total_bytes += len(csv_bytes) + len(json_bytes)
            if total_bytes > max_bytes:
                raise BackupError(
                    f"Backup exceeds the {settings.max_backup_mb} MB limit",
                    code="backup_too_large",
                )

        counts = {
            **export_counts,
            "raw_files": len(raw_entries),
            "raw_files_missing": len(warnings),
            "stream_samples": _count(db, StreamSample),
            "activity_laps": _count(db, ActivityLap),
        }
        created_at = utcnow()
        revision = database_revision(snapshot) or head_revision() or "unknown"
        manifest = {
            "format": BACKUP_FORMAT,
            "format_version": BACKUP_FORMAT_VERSION,
            "app": "Run",
            "app_version": settings.app_version,
            "alembic_revision": revision,
            "alembic_head": head_revision(),
            "created_at": isoformat_z(created_at),
            "database": DATABASE_NAME,
            "counts": counts,
            "files": files,
            "warnings": warnings,
            "total_bytes": total_bytes,
        }

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for entry in files:
                archive.write(sources[entry["path"]], entry["path"])
            archive.writestr(MANIFEST_NAME, _manifest_bytes(manifest))

        filename = f"run-backup-{created_at:%Y%m%d-%H%M%S}.zip"
        return BackupResult(
            path=archive_path,
            filename=filename,
            size_bytes=archive_path.stat().st_size,
            created_at=created_at,
        )
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def validate_backup_zip(zip_path: Path, settings: Settings) -> ValidationResult:
    """Inspect an archive without extracting it into the live data directory."""
    archive_path = Path(zip_path)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    result = ValidationResult(valid=False, archive_size_bytes=_file_size(archive_path))
    max_bytes = max(settings.max_restore_mb, 1) * 1024 * 1024
    if not archive_path.is_file():
        result.errors.append("Backup archive not found")
        return result
    if result.archive_size_bytes > max_bytes:
        result.errors.append(f"Archive exceeds the {settings.max_restore_mb} MB limit")
        return result

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                result.errors.append(f"Archive has more than {MAX_ENTRIES} entries")
                return result

            actual_files: dict[str, zipfile.ZipInfo] = {}
            seen: set[str] = set()
            total_size = 0
            total_compressed = 0
            for info in infos:
                if info.is_dir():
                    continue
                name = info.filename
                path_error = _unsafe_zip_path(name)
                if path_error:
                    result.errors.append(path_error)
                    continue
                if name in seen:
                    result.errors.append(f"Duplicate archive entry: {name}")
                    continue
                seen.add(name)
                if _is_symlink(info):
                    result.errors.append(f"Symbolic links are not allowed: {name}")
                    continue
                if info.flag_bits & 0x1:
                    result.errors.append(f"Encrypted entries are not supported: {name}")
                    continue
                if info.file_size > max_bytes:
                    result.errors.append(f"Entry is larger than the restore limit: {name}")
                    continue
                total_size += info.file_size
                total_compressed += info.compress_size
                actual_files[name] = info

            result.uncompressed_size_bytes = total_size
            if total_size > max_bytes:
                result.errors.append(
                    f"Uncompressed backup exceeds the {settings.max_restore_mb} MB limit"
                )
            if (
                total_size > COMPRESSION_RATIO_MIN_BYTES
                and total_compressed > 0
                and total_size / total_compressed > COMPRESSION_RATIO_LIMIT
            ):
                result.errors.append("Archive looks like a zip bomb (compression ratio too high)")
            if result.errors:
                return result

            if MANIFEST_NAME not in actual_files:
                result.errors.append("manifest.json is missing")
                return result
            manifest_info = actual_files[MANIFEST_NAME]
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                result.errors.append("manifest.json is too large")
                return result
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                result.errors.append(f"manifest.json is not valid JSON: {exc}")
                return result
            if not isinstance(manifest, dict):
                result.errors.append("manifest.json must contain an object")
                return result
            result.manifest = manifest

            revision = manifest.get("alembic_revision")
            head = head_revision()
            if not isinstance(revision, str) or not revision:
                result.errors.append("manifest.json has no Alembic revision")
            elif head and revision != head:
                result.errors.append(f"Backup revision {revision} is not compatible with {head}")

            manifest_files = manifest.get("files")
            if not isinstance(manifest_files, list) or not manifest_files:
                result.errors.append("manifest.json has no file list")
                return result
            expected: dict[str, dict[str, Any]] = {}
            for entry in manifest_files:
                if not isinstance(entry, dict):
                    result.errors.append("manifest.json contains an invalid file entry")
                    continue
                path = entry.get("path")
                if not isinstance(path, str) or _unsafe_zip_path(path):
                    result.errors.append(f"Unsafe manifest path: {path!r}")
                    continue
                if path in expected:
                    result.errors.append(f"Duplicate manifest path: {path}")
                    continue
                expected[path] = entry
            if DATABASE_NAME not in expected:
                result.errors.append(f"{DATABASE_NAME} is missing from the manifest")
            if manifest.get("database") != DATABASE_NAME:
                result.errors.append("Manifest database entry is not run.db")

            actual = set(actual_files) - {MANIFEST_NAME}
            missing = sorted(set(expected) - actual)
            extra = sorted(actual - set(expected))
            if missing:
                result.errors.append(
                    f"Files listed in the manifest are missing: {', '.join(missing[:5])}"
                )
            if extra:
                result.errors.append(f"Archive contains undeclared files: {', '.join(extra[:5])}")

            for name, entry in expected.items():
                info = actual_files.get(name)
                if info is None:
                    continue
                size = entry.get("size")
                digest = entry.get("sha256")
                if not isinstance(size, int) or size != info.file_size:
                    result.errors.append(f"Size mismatch for {name}")
                    continue
                if not isinstance(digest, str) or not digest:
                    result.errors.append(f"Missing checksum for {name}")
                    continue
                computed = _sha256_zip_entry(archive, info)
                if computed != digest:
                    result.errors.append(f"Checksum mismatch for {name}")

            kind_errors = _validate_entry_kinds(expected)
            result.errors.extend(kind_errors)
            if result.errors:
                return result

            table_errors, table_warnings = _validate_database(
                archive,
                actual_files[DATABASE_NAME],
                manifest,
                settings,
            )
            result.errors.extend(table_errors)
            result.warnings.extend(table_warnings)
            result.file_count = len(actual)
            result.valid = not result.errors
            return result
    except zipfile.BadZipFile:
        result.errors.append("File is not a valid ZIP archive")
    except OSError as exc:
        result.errors.append(f"Could not read the backup archive: {exc}")
    return result


def stage_pending_restore(
    zip_path: Path,
    original_filename: str,
    settings: Settings,
) -> PendingRestore:
    """Validate and copy an archive into the pending restore directory."""
    settings.ensure_dirs()
    pending_dir = settings.restore_pending_dir
    if pending_dir.exists() and any(pending_dir.iterdir()):
        raise BackupError("A restore is already pending", code="restore_pending")
    if pending_dir.exists():
        pending_dir.rmdir()
    try:
        pending_dir.mkdir(parents=True)
    except FileExistsError as exc:
        raise BackupError("A restore is already pending", code="restore_pending") from exc

    archive_path = pending_dir / PENDING_ARCHIVE_NAME
    try:
        shutil.copyfile(zip_path, archive_path)
        validation = validate_backup_zip(archive_path, settings)
        if not validation.valid:
            raise BackupError(
                "The backup is not valid",
                code="invalid_backup",
                errors=validation.errors,
            )
        staged_at = utcnow()
        payload = {
            "staged_at": isoformat_z(staged_at),
            "original_filename": Path(original_filename or "backup.zip").name,
            "archive_size_bytes": archive_path.stat().st_size,
            "archive_sha256": sha256_file(archive_path),
            "manifest": validation.manifest,
            "warnings": validation.warnings,
        }
        _write_json_atomic(pending_dir / PENDING_METADATA_NAME, payload)
        return PendingRestore(
            directory=pending_dir,
            archive_path=archive_path,
            staged_at=staged_at,
            original_filename=payload["original_filename"],
            archive_size_bytes=payload["archive_size_bytes"],
            archive_sha256=payload["archive_sha256"],
            manifest=validation.manifest,
            warnings=validation.warnings,
        )
    except Exception:
        shutil.rmtree(pending_dir, ignore_errors=True)
        raise


def pending_restore(settings: Settings) -> PendingRestore | None:
    pending_dir = settings.restore_pending_dir
    metadata_path = pending_dir / PENDING_METADATA_NAME
    archive_path = pending_dir / PENDING_ARCHIVE_NAME
    if not metadata_path.is_file() or not archive_path.is_file():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read pending restore metadata at %s", metadata_path)
        return None
    staged_at = _parse_datetime(payload.get("staged_at"))
    if staged_at is None:
        staged_at = utcnow()
    return PendingRestore(
        directory=pending_dir,
        archive_path=archive_path,
        staged_at=staged_at,
        original_filename=str(payload.get("original_filename") or "backup.zip"),
        archive_size_bytes=int(payload.get("archive_size_bytes") or 0),
        archive_sha256=str(payload.get("archive_sha256") or ""),
        manifest=payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None,
        warnings=[str(item) for item in payload.get("warnings") or []],
    )


def clear_pending_restore(settings: Settings) -> bool:
    pending_dir = settings.restore_pending_dir
    if not pending_dir.exists():
        return False
    shutil.rmtree(pending_dir)
    return True


def apply_pending_restore(settings: Settings) -> ApplyRestoreResult:
    """Apply a pending restore. Must only run while the application is stopped."""
    pending = pending_restore(settings)
    if pending is None:
        return ApplyRestoreResult(applied=False, message="No pending restore")

    validation = validate_backup_zip(pending.archive_path, settings)
    if not validation.valid:
        raise BackupError(
            "The pending restore is not valid",
            code="invalid_backup",
            errors=validation.errors,
        )

    settings.ensure_dirs()
    applied_at = utcnow()
    timestamp = applied_at.strftime("%Y%m%dT%H%M%SZ")
    staging = settings.restore_dir / f"apply-{timestamp}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    raw_staging = staging / "raw"
    raw_staging.mkdir()
    db_staging = staging / DATABASE_NAME
    _extract_archive(pending.archive_path, db_staging, raw_staging)

    db_path = database_path(settings)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    pre_restore = db_path.with_name(f"{db_path.name}.pre-restore-{timestamp}")
    raw_dir = settings.raw_dir
    raw_previous = settings.restore_dir / f"raw.pre-restore-{timestamp}"
    db_replaced = False
    raw_replaced = False
    try:
        if db_path.exists():
            _snapshot_sqlite(db_path, pre_restore)
        if raw_dir.exists():
            os.replace(raw_dir, raw_previous)
        os.replace(raw_staging, raw_dir)
        raw_replaced = True

        new_db = db_path.with_name(f".{db_path.name}.restore-{timestamp}")
        shutil.copyfile(db_staging, new_db)
        _fsync_path(new_db)
        os.replace(new_db, db_path)
        db_replaced = True
        for suffix in ("-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    except Exception:
        if db_replaced and pre_restore.exists():
            shutil.copyfile(pre_restore, db_path)
        if raw_replaced and raw_dir.exists():
            shutil.rmtree(raw_dir, ignore_errors=True)
        if raw_previous.exists() and not raw_dir.exists():
            os.replace(raw_previous, raw_dir)
        raise

    marker = {
        "status": "applied",
        "applied_at": isoformat_z(applied_at),
        "pre_restore_database": str(pre_restore),
        "original_filename": pending.original_filename,
        "archive_sha256": pending.archive_sha256,
        "manifest": validation.manifest,
        "warnings": validation.warnings,
    }
    _write_json_atomic(settings.restore_marker_path, marker)
    shutil.rmtree(pending.directory, ignore_errors=True)
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(raw_previous, ignore_errors=True)
    return ApplyRestoreResult(
        applied=True,
        message="Pending restore applied",
        applied_at=applied_at,
        pre_restore_database=pre_restore,
        manifest=validation.manifest,
    )


def last_restore_marker(settings: Settings) -> dict[str, Any] | None:
    path = settings.restore_marker_path
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


# ---------------------------------------------------------------------------
# Database and file helpers


def database_path(settings: Settings) -> Path:
    try:
        url = make_url(settings.resolved_database_url)
    except Exception as exc:  # noqa: BLE001 - invalid URL is a configuration error
        raise BackupError(f"Invalid database URL: {exc}") from exc
    if not url.drivername.startswith("sqlite"):
        raise BackupError("Backup/restore only supports the SQLite database")
    if not url.database or url.database == ":memory:":
        raise BackupError("Backup/restore needs a file-backed SQLite database")
    path = Path(url.database)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


@lru_cache(maxsize=1)
def head_revision() -> str | None:
    """Alembic head bundled with this application, if available."""
    root = Path(__file__).resolve().parents[2]
    config_path = root / "alembic.ini"
    if not config_path.is_file():
        return None
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(config_path))
        config.set_main_option("script_location", str(root / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception as exc:  # noqa: BLE001 - optional in minimal installs
        logger.warning("Could not read the Alembic head revision: %s", exc)
        return None


def database_revision(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        with _sqlite_ro(path) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            return str(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return None


def _snapshot_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    try:
        with _sqlite_ro(source) as source_connection:
            destination = sqlite3.connect(str(target), timeout=30)
            try:
                source_connection.backup(destination)
                destination.execute("PRAGMA journal_mode=DELETE")
                destination.commit()
            finally:
                destination.close()
    except sqlite3.Error as exc:
        raise BackupError(f"Could not snapshot the SQLite database: {exc}") from exc


def _sqlite_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30)


def _backup_raw_files(
    settings: Settings,
    db: Session,
    warnings: list[str],
) -> list[tuple[Path, str]]:
    rows = db.scalars(select(RawFile).order_by(RawFile.id)).all()
    result: list[tuple[Path, str]] = []
    seen: set[str] = set()
    root = settings.data_dir.resolve()
    for row in rows:
        relative = PurePosixPath(row.storage_path or "")
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] != "raw"
        ):
            warnings.append(f"raw_path_rejected:{row.id}")
            continue
        archive_name = relative.as_posix()
        if archive_name in seen:
            continue
        source = (settings.data_dir / Path(*relative.parts)).resolve()
        if root not in source.parents or not source.is_file():
            warnings.append(f"raw_file_missing:{row.id}")
            continue
        seen.add(archive_name)
        result.append((source, archive_name))
    return result


def _table_rows(db: Session, model: type[Any]) -> list[dict[str, Any]]:
    columns = [column.name for column in model.__table__.columns]
    rows: list[dict[str, Any]] = []
    result = db.execute(select(model)).scalars()
    for item in result:
        rows.append({name: getattr(item, name) for name in columns})
    return rows


def _rows_to_csv(model: type[Any], rows: list[dict[str, Any]]) -> bytes:
    columns = [column.name for column in model.__table__.columns]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key)) for key in columns})
    return buffer.getvalue().encode("utf-8")


def _rows_to_json(rows: list[dict[str, Any]]) -> bytes:
    payload = [{key: _json_value(value) for key, value in row.items()} for row in rows]
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _add_bytes(
    work_dir: Path,
    files: list[dict[str, Any]],
    archive_name: str,
    kind: str,
    data: bytes,
) -> Path:
    target = work_dir / Path(*PurePosixPath(archive_name).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    files.append(
        {
            "path": archive_name,
            "kind": kind,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    )
    return target


def _count(db: Session, model: type[Any]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _validate_entry_kinds(expected: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for name, entry in expected.items():
        kind = entry.get("kind")
        if kind == "database" and name != DATABASE_NAME:
            errors.append("Only run.db may use the database kind")
        elif kind == "raw" and not name.startswith("raw/"):
            errors.append(f"Raw file is outside raw/: {name}")
        elif kind == "export" and not name.startswith("exports/"):
            errors.append(f"Export file is outside exports/: {name}")
        elif kind not in {"database", "raw", "export"}:
            errors.append(f"Unknown file kind for {name}")
    return errors


def _validate_database(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    manifest: dict[str, Any],
    settings: Settings,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="run-restore-check-", dir=settings.tmp_dir))
    snapshot = temp_dir / DATABASE_NAME
    try:
        with archive.open(info) as source, snapshot.open("wb") as target:
            shutil.copyfileobj(source, target, length=HASH_CHUNK)
        try:
            with _sqlite_ro(snapshot) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchall()
                if integrity != [("ok",)]:
                    errors.append("SQLite integrity check failed")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                missing = sorted(set(Base.metadata.tables) - tables)
                if missing:
                    errors.append(f"Expected tables are missing: {', '.join(missing)}")
                foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
                if foreign:
                    errors.append("SQLite foreign key check failed")
                if "alembic_version" in tables:
                    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
                    snapshot_revision = str(row[0]) if row and row[0] else None
                    if snapshot_revision != manifest.get("alembic_revision"):
                        errors.append("Snapshot Alembic revision does not match the manifest")
                counts = manifest.get("counts")
                if isinstance(counts, dict) and "activities" in counts and "activities" in tables:
                    actual = connection.execute("SELECT COUNT(*) FROM activities").fetchone()
                    if actual and int(actual[0]) != counts.get("activities"):
                        warnings.append("Manifest activity count does not match the snapshot")
        except sqlite3.Error as exc:
            errors.append(f"Snapshot is not a valid SQLite database: {exc}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return errors, warnings


def _extract_archive(archive_path: Path, database_target: Path, raw_target: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        validation_manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        entries = validation_manifest.get("files")
        if not isinstance(entries, list):
            raise BackupError("Backup manifest has no file list")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("path")
            if not isinstance(name, str) or _unsafe_zip_path(name):
                raise BackupError(f"Unsafe restore path: {name!r}")
            if name == DATABASE_NAME:
                target = database_target
            elif name.startswith("raw/"):
                target = raw_target / Path(*PurePosixPath(name).parts[1:])
            elif name.startswith("exports/"):
                continue
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=HASH_CHUNK)
            _fsync_path(target)


def _unsafe_zip_path(name: str) -> str | None:
    if not name:
        return "Unsafe empty path"
    if name == MANIFEST_NAME:
        return None
    if "\\" in name or name.startswith("/"):
        return f"Unsafe absolute or backslash path: {name}"
    pure = PurePosixPath(name)
    if pure.is_absolute():
        return f"Unsafe absolute path: {name}"
    if any(part in {"", ".", ".."} for part in pure.parts):
        return f"Unsafe path traversal: {name}"
    if pure.as_posix() != name:
        return f"Unsafe path normalization: {name}"
    return None


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _sha256_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info) as source:
        while chunk := source.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _fsync_path(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError:
        pass


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def isoformat_z(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat(timespec="seconds") + "Z"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def manifest_summary(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    total_bytes = sum(int(item.get("size") or 0) for item in files if isinstance(item, dict))
    counts = manifest.get("counts")
    return {
        "format": str(manifest.get("format") or ""),
        "format_version": int(manifest.get("format_version") or 0),
        "app_version": str(manifest.get("app_version") or ""),
        "alembic_revision": str(manifest.get("alembic_revision") or ""),
        "created_at": str(manifest.get("created_at") or ""),
        "counts": counts if isinstance(counts, dict) else {},
        "file_count": len(files),
        "total_bytes": total_bytes,
        "warnings": [str(item) for item in manifest.get("warnings") or []],
    }
