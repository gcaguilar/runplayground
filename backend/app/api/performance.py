"""Performance predictions, goals and historical snapshots (M1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Activity
from app.schemas import (
    GarminReference,
    GoalArchiveOut,
    GoalCloseRequest,
    GoalOut,
    GoalUpsert,
    PerformanceHistory,
    PerformanceOverview,
    PerformanceRecomputeResponse,
)
from app.services.performance import (
    build_overview,
    close_goal,
    delete_goal,
    ensure_efforts,
    garmin_reference,
    get_history,
    list_goal_archive,
    list_goals,
    mark_efforts_refreshed,
    refresh_all_efforts,
    store_snapshot,
    upsert_goal,
)
from app.services.performance_models import DISTANCE_BY_KEY

router = APIRouter(prefix="/performance", tags=["performance"])


def _distance_or_404(distance_key: str) -> float:
    distance = DISTANCE_BY_KEY.get(distance_key)
    if distance is None:
        raise HTTPException(status_code=404, detail="Unknown standard distance")
    return distance


@router.get("", response_model=PerformanceOverview)
def performance_overview(db: Session = Depends(get_db)) -> PerformanceOverview:
    ensure_efforts(db)
    overview = build_overview(db)
    store_snapshot(db, overview)
    return overview


@router.post("/recompute", response_model=PerformanceRecomputeResponse)
def recompute_performance(db: Session = Depends(get_db)) -> PerformanceRecomputeResponse:
    activities, efforts = refresh_all_efforts(db)
    mark_efforts_refreshed(db, activities, efforts)
    db.commit()
    overview = build_overview(db)
    store_snapshot(db, overview)
    return PerformanceRecomputeResponse(
        activities=activities,
        efforts=efforts,
        overview=overview,
    )


@router.get("/history", response_model=PerformanceHistory)
def performance_history(
    days: int = Query(180, ge=30, le=730),
    db: Session = Depends(get_db),
) -> PerformanceHistory:
    return get_history(db, days)


@router.get("/goals", response_model=list[GoalOut])
def performance_goals(db: Session = Depends(get_db)) -> list[GoalOut]:
    return list_goals(db)


@router.get("/goals/archive", response_model=list[GoalArchiveOut])
def performance_goal_archive(db: Session = Depends(get_db)) -> list[GoalArchiveOut]:
    return list_goal_archive(db)


def _check_activity(db: Session, activity_id: int | None) -> None:
    if activity_id is not None and db.get(Activity, activity_id) is None:
        raise HTTPException(status_code=404, detail="Activity not found")


@router.post("/goals/{distance_key}/close", response_model=GoalArchiveOut)
def close_performance_goal(
    distance_key: str,
    payload: GoalCloseRequest,
    db: Session = Depends(get_db),
) -> GoalArchiveOut:
    distance = _distance_or_404(distance_key)
    _check_activity(db, payload.activity_id)
    archived = close_goal(db, distance, payload)
    if archived is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return archived


@router.put("/goals/{distance_key}", response_model=GoalOut)
def put_performance_goal(
    distance_key: str,
    payload: GoalUpsert,
    db: Session = Depends(get_db),
) -> GoalOut:
    distance = _distance_or_404(distance_key)
    return upsert_goal(db, distance, payload)


@router.delete("/goals/{distance_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_performance_goal(
    distance_key: str,
    db: Session = Depends(get_db),
) -> Response:
    distance = _distance_or_404(distance_key)
    if not delete_goal(db, distance):
        raise HTTPException(status_code=404, detail="Goal not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reference", response_model=GarminReference)
def performance_reference(db: Session = Depends(get_db)) -> GarminReference:
    return garmin_reference(db)
