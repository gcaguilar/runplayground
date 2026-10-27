"""Diagnostics, training plan and analysis settings endpoints (M2/M11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    AnalysisSettingsOut,
    AnalysisSettingsUpdate,
    DiagnosticsOverview,
    TrainingPlan,
)
from app.services.analysis_settings import get_analysis_settings, put_analysis_settings
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


@router.get("/analysis/settings", response_model=AnalysisSettingsOut)
def analysis_settings(db: Session = Depends(get_db)) -> AnalysisSettingsOut:
    ensure_efforts(db)
    return get_analysis_settings(db).response


@router.put("/analysis/settings", response_model=AnalysisSettingsOut)
def update_analysis_settings(
    payload: AnalysisSettingsUpdate,
    db: Session = Depends(get_db),
) -> AnalysisSettingsOut:
    ensure_efforts(db)
    try:
        return put_analysis_settings(db, payload).response
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
