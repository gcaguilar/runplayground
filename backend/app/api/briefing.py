"""Weekly briefing endpoint (M5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BriefingView
from app.services.briefing import build_briefing

router = APIRouter(tags=["briefing"])


@router.get("/briefing", response_model=BriefingView)
def briefing(
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> BriefingView:
    return build_briefing(db, tz_offset_minutes=tz_offset_minutes)
