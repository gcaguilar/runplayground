"""Recovery context endpoints (M9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import RecoveryOverview
from app.services.recovery import build_recovery

router = APIRouter(tags=["recovery"])


@router.get("/recovery", response_model=RecoveryOverview)
def recovery(
    days: int = Query(90, ge=7, le=730),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> RecoveryOverview:
    return build_recovery(db, days=days, tz_offset_minutes=tz_offset_minutes)
