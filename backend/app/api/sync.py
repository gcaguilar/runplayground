"""Garmin sync endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import IngestRun
from app.schemas import (
    StartSyncRequest,
    StartSyncResponse,
    SyncRunOut,
    SyncStatus,
)
from app.services.garmin import GarminAuth
from app.services.sync import manager

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("", response_model=StartSyncResponse)
def start_sync(
    payload: StartSyncRequest,
    settings: Settings = Depends(get_settings),
) -> StartSyncResponse:
    if not settings.garmin_configured:
        raise HTTPException(
            status_code=400,
            detail="GARMIN_PERSONAL_API_KEY is not configured in .env",
        )
    started, run_id, message = manager.start(payload.mode)
    if not started and "already running" not in message.lower():
        raise HTTPException(status_code=409, detail=message)
    return StartSyncResponse(started=started, run_id=run_id, message=message)


@router.get("/status", response_model=SyncStatus)
def sync_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SyncStatus:
    state = manager.status()
    last = db.scalar(
        select(IngestRun)
        .where(IngestRun.kind == "garmin_sync")
        .order_by(IngestRun.id.desc())
        .limit(1)
    )
    last_run = _run_out(last) if last else None
    next_sync_at = None
    if last and last.finished_at and settings.sync_interval_hours > 0:
        next_sync_at = last.finished_at + timedelta(hours=settings.sync_interval_hours)

    auth = GarminAuth(settings)
    token = auth.peek()
    return SyncStatus(
        running=state["running"],
        current_run_id=state["current_run_id"],
        mode=state["mode"],
        last_run=last_run,
        interval_hours=settings.sync_interval_hours,
        next_sync_at=next_sync_at,
        garmin_configured=settings.garmin_configured,
        token={
            "configured": settings.garmin_configured,
            "cached": token is not None,
            "expires_at": token.expires_at if token else None,
            "expires_in_seconds": int(token.expires_in) if token else None,
        },
    )


def _run_out(run: IngestRun) -> SyncRunOut:
    details = run.details or {}
    errors = details.get("errors") if isinstance(details, dict) else None
    return SyncRunOut(
        id=run.id,
        kind=run.kind,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        activities_seen=run.activities_seen,
        activities_created=run.activities_created,
        activities_updated=run.activities_updated,
        activities_skipped=run.activities_skipped,
        files_downloaded=run.files_downloaded,
        errors_count=run.errors_count,
        message=run.message,
        errors=[str(error) for error in (errors or [])],
    )
