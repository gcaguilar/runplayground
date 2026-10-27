"""Backup export and staged restore endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.db import get_db
from app.models import IngestRun
from app.schemas import (
    BackupPendingOut,
    BackupRestoreOut,
    BackupStatusOut,
    BackupValidationOut,
)
from app.services.backup import (
    HASH_CHUNK,
    BackupError,
    clear_pending_restore,
    create_backup,
    database_path,
    database_revision,
    head_revision,
    last_restore_marker,
    pending_restore,
    stage_pending_restore,
    validate_backup_zip,
)
from app.services.sync import manager

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get(
    "/export",
    response_class=FileResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def export_backup(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    try:
        result = create_backup(settings, db)
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return FileResponse(
        result.path,
        media_type="application/zip",
        filename=result.filename,
        background=BackgroundTask(_cleanup_export, result.path.parent),
    )


@router.post(
    "/validate",
    response_model=BackupValidationOut,
    responses={400: {"model": BackupValidationOut}},
)
async def validate_backup(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    archive = await _receive_upload(file, settings, "restore")
    try:
        validation = await run_in_threadpool(validate_backup_zip, archive, settings)
    finally:
        archive.unlink(missing_ok=True)
    return JSONResponse(
        status_code=200 if validation.valid else 400,
        content=validation.payload(),
    )


@router.post("/restore", response_model=BackupRestoreOut)
async def stage_restore(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BackupRestoreOut:
    _reject_if_blocked(db, settings)
    archive = await _receive_upload(file, settings, "restore")
    try:
        pending = await run_in_threadpool(
            stage_pending_restore,
            archive,
            file.filename or "backup.zip",
            settings,
        )
    except BackupError as exc:
        status = 409 if exc.code == "restore_pending" else 400
        raise HTTPException(
            status_code=status,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc
    finally:
        archive.unlink(missing_ok=True)
    return BackupRestoreOut(
        staged=True,
        message="Restore staged. Restart Run to apply it before migrations run.",
        pending=BackupPendingOut(**pending.payload()),
    )


@router.get("/status", response_model=BackupStatusOut)
def backup_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BackupStatusOut:
    pending = pending_restore(settings)
    active = _active_ingest(db)
    try:
        revision = database_revision(database_path(settings))
    except BackupError:
        revision = None
    return BackupStatusOut(
        pending=BackupPendingOut(**pending.payload()) if pending else None,
        last_restore=last_restore_marker(settings),
        max_backup_mb=settings.max_backup_mb,
        max_restore_mb=settings.max_restore_mb,
        database_revision=revision or head_revision(),
        head_revision=head_revision(),
        sync_running=manager.running,
        active_ingest=active,
        data_dir=str(settings.data_dir),
    )


@router.delete("/pending", status_code=status.HTTP_204_NO_CONTENT)
def cancel_pending_restore(
    settings: Settings = Depends(get_settings),
) -> Response:
    if not clear_pending_restore(settings):
        raise HTTPException(status_code=404, detail="There is no pending restore")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers


async def _receive_upload(upload: UploadFile, settings: Settings, label: str) -> Path:
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = max(settings.max_restore_mb, 1) * 1024 * 1024
    target = settings.tmp_dir / f"{label}-{uuid4().hex}.zip"
    size = 0
    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(HASH_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.max_restore_mb} MB limit",
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="File is empty")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return target


def _reject_if_blocked(db: Session, settings: Settings) -> None:
    pending_dir = settings.restore_pending_dir
    has_pending_files = pending_dir.exists() and any(pending_dir.iterdir())
    if pending_restore(settings) is not None or has_pending_files:
        raise HTTPException(status_code=409, detail="A restore is already pending")
    if manager.running:
        raise HTTPException(status_code=409, detail="A Garmin sync is running")
    active = _active_ingest(db)
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An import or sync is running ({active['kind']} #{active['id']})",
        )


def _active_ingest(db: Session) -> dict | None:
    run = db.scalar(
        select(IngestRun)
        .where(IngestRun.status == "running")
        .order_by(IngestRun.id.desc())
        .limit(1)
    )
    if run is None:
        return None
    return {"id": run.id, "kind": run.kind, "mode": run.mode, "started_at": run.started_at}


def _cleanup_export(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
