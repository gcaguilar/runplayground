"""Comparable pace–heart-rate analysis endpoint (M6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PaceHrAnalysisOut
from app.services.comparables import build_pace_hr

router = APIRouter(tags=["comparables"])


@router.get("/comparables/pace-hr", response_model=PaceHrAnalysisOut)
def pace_hr(
    days: int = Query(180, ge=30, le=730),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> PaceHrAnalysisOut:
    return build_pace_hr(db, days=days, tz_offset_minutes=tz_offset_minutes)
