"""Manual FIT/TCX/GPX imports."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.db import get_db
from app.models import IngestRun
from app.schemas import (
    GarminExportResponse,
    ImportFileResult,
    ImportResponse,
    ImportRunOut,
)
from app.services.garmin_export import import_garmin_export
from app.services.ingest import ingest_upload
from app.utils import utcnow

router = APIRouter(prefix="/imports", tags=["imports"])

ALLOWED_EXTENSIONS = {".fit", ".tcx", ".gpx"}


@router.post("", response_model=ImportResponse)
async def import_files(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files supplied")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Import at most 20 files at a time")

    run = IngestRun(
        kind="file_import",
        mode="upload",
        status="running",
        started_at=utcnow(),
        message=f"Importing {len(files)} file(s)",
    )
    db.add(run)
    db.commit()

    results: list[ImportFileResult] = []
    max_bytes = settings.max_upload_mb * 1024 * 1024

    for upload in files:
        filename = upload.filename or "unknown"
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix not in ALLOWED_EXTENSIONS:
            results.append(
                ImportFileResult(
                    filename=filename,
                    status="error",
                    message="Unsupported extension; expected .fit, .tcx or .gpx",
                )
            )
            await upload.close()
            continue

        data = await upload.read(max_bytes + 1)
        await upload.close()
        if len(data) > max_bytes:
            results.append(
                ImportFileResult(
                    filename=filename,
                    status="error",
                    message=f"File exceeds the {settings.max_upload_mb} MB limit",
                )
            )
            continue
        if not data:
            results.append(
                ImportFileResult(filename=filename, status="error", message="File is empty")
            )
            continue

        outcome = await run_in_threadpool(
            ingest_upload,
            db,
            filename,
            data,
            upload.content_type,
        )
        results.append(
            ImportFileResult(
                filename=outcome.filename,
                status=outcome.status,
                activity_id=outcome.activity_id,
                message=outcome.message,
                warnings=outcome.warnings,
            )
        )

    errors = sum(1 for result in results if result.status == "error")
    created = sum(1 for result in results if result.status == "imported")
    merged = sum(1 for result in results if result.status == "merged")
    skipped = sum(1 for result in results if result.status == "duplicate")
    if errors and errors == len(results):
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "success"

    run.status = status
    run.finished_at = utcnow()
    run.activities_seen = len(results)
    run.activities_created = created
    run.activities_updated = merged
    run.activities_skipped = skipped
    run.errors_count = errors
    run.message = f"{created} imported, {merged} merged, {skipped} duplicates, {errors} errors"
    run.details = {
        "results": [result.model_dump(mode="json") for result in results],
    }
    db.commit()

    return ImportResponse(run_id=run.id, results=results)


@router.post("/garmin-export", response_model=GarminExportResponse)
async def import_garmin_export_zip(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GarminExportResponse:
    filename = file.filename or "garmin-export.zip"
    if not filename.lower().endswith(".zip"):
        await file.close()
        raise HTTPException(status_code=400, detail="Expected a .zip Garmin data export")
    max_bytes = settings.garmin_export_max_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Export exceeds the {settings.garmin_export_max_mb} MB limit",
        )
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(status_code=400, detail="File is not a valid ZIP archive")

    run = IngestRun(
        kind="garmin_export",
        mode="upload",
        status="running",
        started_at=utcnow(),
        message="Importing Garmin data export",
    )
    db.add(run)
    db.commit()

    result = await run_in_threadpool(import_garmin_export, db, data, filename)

    run.finished_at = utcnow()
    run.activities_seen = result.activities_imported + result.activities_merged
    run.activities_created = result.activities_imported
    run.activities_updated = result.activities_merged
    run.activities_skipped = result.activities_skipped
    run.errors_count = sum(1 for warning in result.warnings if warning.startswith("activity_error"))
    if (
        result.metrics_imported
        or result.metrics_skipped
        or result.activities_imported
        or result.activities_merged
        or result.activities_skipped
    ):
        run.status = "success"
    else:
        run.status = "partial"
    run.message = (
        f"{result.metrics_imported} metrics imported, "
        f"{result.activities_imported} activities imported"
    )
    run.details = {
        "files_scanned": result.files_scanned,
        "metrics_imported": result.metrics_imported,
        "metrics_skipped": result.metrics_skipped,
        "activities_imported": result.activities_imported,
        "activities_merged": result.activities_merged,
        "activities_skipped": result.activities_skipped,
        "warnings": result.warnings,
    }
    db.commit()

    return GarminExportResponse(
        run_id=run.id,
        status=run.status,
        files_scanned=result.files_scanned,
        metrics_imported=result.metrics_imported,
        metrics_skipped=result.metrics_skipped,
        activities_imported=result.activities_imported,
        activities_merged=result.activities_merged,
        activities_skipped=result.activities_skipped,
        warnings=result.warnings,
    )


@router.get("", response_model=list[ImportRunOut])
def list_imports(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[ImportRunOut]:
    runs = db.scalars(
        select(IngestRun)
        .where(IngestRun.kind.in_(("file_import", "garmin_export")))
        .order_by(IngestRun.id.desc())
        .limit(min(max(limit, 1), 100))
    ).all()
    output = []
    for run in runs:
        details = run.details or {}
        raw_results = details.get("results", [])
        results = [ImportFileResult.model_validate(item) for item in raw_results]
        output.append(
            ImportRunOut(
                id=run.id,
                kind=run.kind,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
                message=run.message,
                metrics_imported=int(details.get("metrics_imported", 0) or 0),
                metrics_skipped=int(details.get("metrics_skipped", 0) or 0),
                results=results,
            )
        )
    return output
