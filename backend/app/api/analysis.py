"""Diagnostics and training endpoints (M2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DiagnosticsOverview, TrainingPlan
from app.services.diagnostics import build_diagnostics, build_training_plan
from app.services.performance import ensure_efforts

router = APIRouter(tags=["analysis"])


@router.get("/diagnostics", response_model=DiagnosticsOverview)
def diagnostics_overview(
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> DiagnosticsOverview:
    ensure_efforts(db)
    return build_diagnostics(db, tz_offset_minutes=tz_offset_minutes)


@router.get("/training", response_model=TrainingPlan)
def training_plan(
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> TrainingPlan:
    ensure_efforts(db)
    return build_training_plan(db, tz_offset_minutes=tz_offset_minutes)
