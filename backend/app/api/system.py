"""System status for the settings screen."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Activity, RawFile
from app.schemas import GarminTokenStatus, SystemStatus
from app.services.garmin import GarminAuth
from app.services.state import get_state

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def system_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SystemStatus:
    activity_count = db.scalar(select(func.count(Activity.id))) or 0
    raw_file_count = db.scalar(select(func.count(RawFile.id))) or 0
    auth = GarminAuth(settings)
    token = auth.peek()

    fingerprint = None
    if settings.garmin_personal_api_key:
        key = settings.garmin_personal_api_key.get_secret_value()
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    return SystemStatus(
        app_name=settings.app_name,
        version=settings.app_version,
        auth_mode=settings.auth_mode,
        garmin_configured=settings.garmin_configured,
        garmin_key_fingerprint=fingerprint,
        garmin_token=GarminTokenStatus(
            configured=settings.garmin_configured,
            cached=token is not None,
            expires_at=token.expires_at if token else None,
            expires_in_seconds=int(token.expires_in) if token else None,
        ),
        activity_count=activity_count,
        raw_file_count=raw_file_count,
        database_size_bytes=_database_size(settings),
        data_dir=str(settings.data_dir),
        sync_interval_hours=settings.sync_interval_hours,
        last_sync=get_state(db, "sync", {}) or None,
        supported_formats=["fit", "tcx", "gpx"],
    )


def _database_size(settings: Settings) -> int:
    try:
        url = make_url(settings.resolved_database_url)
    except Exception:
        return 0
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return 0
    path = Path(url.database)
    if not path.is_absolute():
        path = Path.cwd() / path
    total = 0
    for candidate in (path, Path(f"{path}-wal")):
        if candidate.exists():
            total += candidate.stat().st_size
    return total
