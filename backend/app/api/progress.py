"""Progress, calendar, reports and race planning endpoints (M3)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Activity
from app.schemas import (
    CalendarView,
    PlannedRaceCreate,
    PlannedRaceOut,
    PlannedRaceUpdate,
    ProgressOverview,
    ReportOut,
)
from app.services.progress import (
    build_calendar,
    build_progress,
    build_report,
    create_planned_race,
    delete_planned_race,
    list_planned_races,
    race_out,
    update_planned_race,
)
from app.utils import as_utc, utcnow

router = APIRouter(tags=["progress"])


def _check_activity(db: Session, activity_id: int | None) -> None:
    if activity_id is not None and db.get(Activity, activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")


@router.get("/progress", response_model=ProgressOverview)
def progress_overview(
    days: int = Query(180, ge=30, le=730),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> ProgressOverview:
    return build_progress(db, days=days, tz_offset_minutes=tz_offset_minutes)


@router.get("/calendar", response_model=CalendarView)
def calendar_view(
    start: date | None = Query(None),
    weeks: int = Query(6, ge=1, le=12),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> CalendarView:
    today = (as_utc(utcnow()) + timedelta(minutes=tz_offset_minutes)).date()
    anchor = start or today
    anchor = anchor - timedelta(days=anchor.weekday())
    return build_calendar(
        db,
        start=anchor,
        weeks=weeks,
        tz_offset_minutes=tz_offset_minutes,
    )


@router.get("/reports", response_model=ReportOut)
def report(
    period: Literal["week", "month"] = Query("week"),
    date_: date | None = Query(None, alias="date"),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> ReportOut:
    today = (as_utc(utcnow()) + timedelta(minutes=tz_offset_minutes)).date()
    anchor = date_ or today
    return build_report(
        db,
        period=period,
        anchor_date=anchor,
        tz_offset_minutes=tz_offset_minutes,
    )


@router.get("/races", response_model=list[PlannedRaceOut])
def races(
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> list[PlannedRaceOut]:
    return list_planned_races(db, tz_offset_minutes=tz_offset_minutes)


@router.post("/races", response_model=PlannedRaceOut, status_code=status.HTTP_201_CREATED)
def create_race(
    payload: PlannedRaceCreate,
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> PlannedRaceOut:
    _check_activity(db, payload.activity_id)
    race = create_planned_race(db, payload)
    return race_out(db, race, tz_offset_minutes=tz_offset_minutes)


@router.patch("/races/{race_id}", response_model=PlannedRaceOut)
def patch_race(
    race_id: int,
    payload: PlannedRaceUpdate,
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> PlannedRaceOut:
    _check_activity(db, payload.activity_id)
    race = update_planned_race(db, race_id, payload)
    if race is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return race_out(db, race, tz_offset_minutes=tz_offset_minutes)


@router.delete("/races/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_race(race_id: int, db: Session = Depends(get_db)) -> Response:
    if not delete_planned_race(db, race_id):
        raise HTTPException(status_code=404, detail="Race not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
