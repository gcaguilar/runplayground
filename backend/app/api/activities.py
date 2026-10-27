"""Activity list, detail, streams, corrections and deletion."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Activity, StreamSample
from app.schemas import (
    ActivityDetail,
    ActivityList,
    ActivityOut,
    ActivityPatch,
    ActivityStreams,
    ComparisonView,
    LapOut,
    SourceOut,
    StreamPoint,
)
from app.services.comparison import build_comparison
from app.services.performance import refresh_activity_efforts

router = APIRouter(prefix="/activities", tags=["activities"])

SORTS = {
    "date_desc": Activity.start_time_utc.desc(),
    "date_asc": Activity.start_time_utc.asc(),
    "distance_desc": Activity.distance_m.desc(),
    "distance_asc": Activity.distance_m.asc(),
    "duration_desc": Activity.duration_s.desc(),
    "duration_asc": Activity.duration_s.asc(),
}


@router.get("", response_model=ActivityList)
def list_activities(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sport: str | None = None,
    q: str | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    sort: str = "date_desc",
    db: Session = Depends(get_db),
) -> ActivityList:
    filters = []
    if sport:
        filters.append(Activity.sport == sport)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(Activity.name.ilike(pattern))
    if date_from:
        filters.append(Activity.start_time_utc >= datetime.combine(date_from, time.min))
    if date_to:
        filters.append(
            Activity.start_time_utc < datetime.combine(date_to + timedelta(days=1), time.min)
        )

    total = db.scalar(select(func.count(Activity.id)).where(*filters)) or 0
    order = SORTS.get(sort, SORTS["date_desc"])
    items = (
        db.scalars(
            select(Activity)
            .where(*filters)
            .options(selectinload(Activity.sources))
            .order_by(order)
            .limit(limit)
            .offset(offset)
        )
        .unique()
        .all()
    )
    return ActivityList(
        items=[ActivityOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/meta/sports")
def sports_breakdown(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Activity.sport, func.count(Activity.id), func.sum(Activity.distance_m))
        .group_by(Activity.sport)
        .order_by(func.count(Activity.id).desc())
    ).all()
    return [
        {"sport": sport, "activities": count, "distance_m": distance or 0}
        for sport, count, distance in rows
    ]


@router.get("/compare", response_model=ComparisonView)
def compare_activities(
    left_id: int = Query(..., ge=1),
    right_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
) -> ComparisonView:
    if left_id == right_id:
        raise HTTPException(status_code=422, detail="Choose two different activities")
    comparison = build_comparison(db, left_id, right_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return comparison


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, db: Session = Depends(get_db)) -> ActivityDetail:
    return _detail(db, activity_id)


@router.patch("/{activity_id}", response_model=ActivityDetail)
def patch_activity(
    activity_id: int,
    payload: ActivityPatch,
    db: Session = Depends(get_db),
) -> ActivityDetail:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    if payload.name is not None:
        activity.name = payload.name.strip()[:255]
    if payload.is_race is not None and payload.is_race != activity.is_race:
        activity.is_race = payload.is_race
        refresh_activity_efforts(db, activity)
    db.commit()
    return _detail(db, activity_id)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(activity_id: int, db: Session = Depends(get_db)) -> Response:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(activity)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{activity_id}/streams", response_model=ActivityStreams)
def get_streams(
    activity_id: int,
    max_points: int = Query(1500, ge=50, le=5000),
    db: Session = Depends(get_db),
) -> ActivityStreams:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    samples = db.scalars(
        select(StreamSample)
        .where(StreamSample.activity_id == activity_id)
        .order_by(StreamSample.sample_index)
    ).all()
    total = len(samples)
    downsampled = total > max_points
    selected = _downsample(samples, max_points) if downsampled else samples

    first_timestamp = next(
        (sample.timestamp_utc for sample in samples if sample.timestamp_utc),
        None,
    )
    points = []
    for sample in selected:
        elapsed = sample.elapsed_s
        if elapsed is None and sample.timestamp_utc and first_timestamp:
            elapsed = (sample.timestamp_utc - first_timestamp).total_seconds()
        points.append(
            StreamPoint(
                t=round(elapsed, 2) if elapsed is not None else None,
                distance_m=_round(sample.distance_m, 2),
                heart_rate=sample.heart_rate,
                cadence_spm=_round(sample.cadence_spm, 1),
                speed_mps=_round(sample.speed_mps, 3),
                elevation_m=_round(sample.elevation_m, 1),
                latitude=_round(sample.latitude, 6),
                longitude=_round(sample.longitude, 6),
                power_w=_round(sample.power_w, 1),
                temperature_c=_round(sample.temperature_c, 1),
            )
        )
    return ActivityStreams(
        activity_id=activity_id,
        total_points=total,
        downsampled=downsampled,
        points=points,
    )


def _detail(db: Session, activity_id: int) -> ActivityDetail:
    activity = db.scalar(
        select(Activity)
        .where(Activity.id == activity_id)
        .options(selectinload(Activity.sources), selectinload(Activity.laps))
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    base = ActivityOut.model_validate(activity)
    return ActivityDetail(
        **base.model_dump(),
        laps=[LapOut.model_validate(lap) for lap in activity.laps],
        sources=[SourceOut.from_orm_source(source) for source in activity.sources],
    )


def _downsample(samples: list[StreamSample], max_points: int) -> list[StreamSample]:
    if max_points <= 1 or len(samples) <= max_points:
        return samples
    indices = {round(index * (len(samples) - 1) / (max_points - 1)) for index in range(max_points)}
    return [samples[index] for index in sorted(indices)]


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None
