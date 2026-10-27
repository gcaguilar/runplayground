"""Future scenarios and continuous tracking endpoints (M4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    ActionUpsert,
    ForecastView,
    TrackedActionOut,
    TrackingOverview,
)
from app.services.forecast import build_forecast
from app.services.tracking import (
    build_tracking,
    delete_action,
    upsert_action,
)

router = APIRouter(tags=["tracking"])


@router.get("/forecast", response_model=ForecastView)
def forecast(
    weeks: int = Query(8),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> ForecastView:
    if weeks not in (8, 12):
        raise HTTPException(status_code=422, detail="Forecast horizon must be 8 or 12 weeks")
    return build_forecast(db, weeks=weeks, tz_offset_minutes=tz_offset_minutes)


@router.get("/tracking", response_model=TrackingOverview)
def tracking(
    days: int = Query(180, ge=30, le=730),
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> TrackingOverview:
    return build_tracking(db, days=days, tz_offset_minutes=tz_offset_minutes)


@router.put("/tracking/actions/{dimension_key}", response_model=TrackedActionOut)
def put_action(
    dimension_key: str,
    payload: ActionUpsert,
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> TrackedActionOut:
    action = upsert_action(db, dimension_key, payload)
    if action is None:
        raise HTTPException(status_code=404, detail="Unknown training dimension")
    overview = build_tracking(db, tz_offset_minutes=tz_offset_minutes)
    item = next(
        (candidate for candidate in overview.actions if candidate.dimension_key == dimension_key),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Tracked action not found")
    return item


@router.delete("/tracking/actions/{dimension_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_action(dimension_key: str, db: Session = Depends(get_db)) -> Response:
    if not delete_action(db, dimension_key):
        raise HTTPException(status_code=404, detail="Tracked action not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
