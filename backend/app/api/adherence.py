"""Suggested-plan adherence endpoint (M10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AdherenceOverview
from app.services.adherence import ALLOWED_WEEKS, build_adherence

router = APIRouter(tags=["adherence"])


@router.get("/adherence", response_model=AdherenceOverview)
def adherence(
    weeks: int = Query(8),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> AdherenceOverview:
    if weeks not in ALLOWED_WEEKS:
        raise HTTPException(status_code=422, detail="Adherence window must be 4, 8 or 12 weeks")
    return build_adherence(db, weeks=weeks, tz_offset_minutes=tz_offset_minutes)
