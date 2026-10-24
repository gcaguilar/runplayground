"""Manual FIT/TCX/GPX imports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.db import get_db
from app.models import IngestRun
from app.schemas import ImportFileResult, ImportResponse, ImportRunOut
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


@router.get("", response_model=list[ImportRunOut])
def list_imports(
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[ImportRunOut]:
    runs = db.scalars(
        select(IngestRun)
        .where(IngestRun.kind == "file_import")
        .order_by(IngestRun.id.desc())
        .limit(min(max(limit, 1), 100))
    ).all()
    output = []
    for run in runs:
        raw_results = (run.details or {}).get("results", [])
        results = [ImportFileResult.model_validate(item) for item in raw_results]
        output.append(
            ImportRunOut(
                id=run.id,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
                message=run.message,
                results=results,
            )
        )
    return output
