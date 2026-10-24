"""Weekly aggregation used by the dashboard's Resumen section."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Activity
from app.schemas import SportTotal, WeeklyDay, WeeklySummary, WeeklyTotals
from app.utils import as_utc

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/weekly", response_model=WeeklySummary)
def weekly_summary(
    week_start: date | None = None,
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> WeeklySummary:
    offset = timedelta(minutes=tz_offset_minutes)
    if week_start is None:
        today_local = (datetime.now() + offset).date()
        week_start = today_local - timedelta(days=today_local.weekday())
    else:
        week_start = week_start - timedelta(days=week_start.weekday())

    current = _aggregate(db, week_start, offset)
    previous = _aggregate(db, week_start - timedelta(days=7), offset)

    return WeeklySummary(
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        totals=current["totals"],
        previous=previous["totals"],
        delta={
            "distance_pct": _pct(current["totals"].distance_m, previous["totals"].distance_m),
            "duration_pct": _pct(current["totals"].duration_s, previous["totals"].duration_s),
            "activities_pct": _pct(current["totals"].activities, previous["totals"].activities),
            "elevation_pct": _pct(
                current["totals"].elevation_gain_m, previous["totals"].elevation_gain_m
            ),
        },
        days=current["days"],
        by_sport=current["by_sport"],
    )


def _aggregate(db: Session, week_start: date, offset: timedelta) -> dict:
    start_utc = datetime.combine(week_start, time.min) - offset
    end_utc = start_utc + timedelta(days=7)
    activities = db.scalars(
        select(Activity)
        .where(Activity.start_time_utc >= start_utc, Activity.start_time_utc < end_utc)
        .order_by(Activity.start_time_utc)
    ).all()

    day_map: dict[date, dict] = {
        week_start + timedelta(days=index): {"activities": 0, "distance_m": 0.0, "duration_s": 0.0}
        for index in range(7)
    }
    sport_map: dict[str, dict] = defaultdict(
        lambda: {"activities": 0, "distance_m": 0.0, "duration_s": 0.0}
    )

    distance = duration = elevation = 0.0
    longest_distance = longest_duration = 0.0
    hr_weighted = 0.0
    hr_duration = 0.0

    for activity in activities:
        local_day = (as_utc(activity.start_time_utc) + offset).date()
        day = day_map.get(local_day)
        if day is not None:
            day["activities"] += 1
            day["distance_m"] += activity.distance_m
            day["duration_s"] += activity.duration_s

        sport = sport_map[activity.sport]
        sport["activities"] += 1
        sport["distance_m"] += activity.distance_m
        sport["duration_s"] += activity.duration_s

        distance += activity.distance_m
        duration += activity.duration_s
        elevation += activity.elevation_gain_m or 0
        longest_distance = max(longest_distance, activity.distance_m)
        longest_duration = max(longest_duration, activity.duration_s)
        if activity.avg_hr and activity.duration_s > 0:
            hr_weighted += activity.avg_hr * activity.duration_s
            hr_duration += activity.duration_s

    active_days = sum(1 for day in day_map.values() if day["activities"] > 0)
    totals = WeeklyTotals(
        activities=len(activities),
        distance_m=round(distance, 1),
        duration_s=round(duration, 1),
        elevation_gain_m=round(elevation, 1),
        active_days=active_days,
        avg_hr=round(hr_weighted / hr_duration, 1) if hr_duration else None,
        longest_distance_m=round(longest_distance, 1),
        longest_duration_s=round(longest_duration, 1),
    )
    days = [
        WeeklyDay(
            date=day,
            activities=values["activities"],
            distance_m=round(values["distance_m"], 1),
            duration_s=round(values["duration_s"], 1),
        )
        for day, values in day_map.items()
    ]
    by_sport = [
        SportTotal(
            sport=sport,
            activities=values["activities"],
            distance_m=round(values["distance_m"], 1),
            duration_s=round(values["duration_s"], 1),
        )
        for sport, values in sorted(
            sport_map.items(), key=lambda item: item[1]["distance_m"], reverse=True
        )
    ]
    return {"totals": totals, "days": days, "by_sport": by_sport}


def _pct(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)
