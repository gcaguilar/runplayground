"""Adherence to the suggested weekly training plan (M10).

The training plan is derived, not a registered plan: there is no stored
"planned session" table. This module reconstructs what the plan would have
suggested for each recent week from the phase at that week's start, the
28-day base volume before it and the standard session builder. It then compares
that suggestion with what was actually run.

Adherence is deliberately a heuristic:

* the plan is reconstructed, so it is not a signed coach plan;
* a current week is marked in progress and excluded from the score;
* a long run scheduled for Saturday is not "missed" on Wednesday;
* the intensity classification uses the current anchor, not a historical one;
* rest is derived from the absence of running, not from a calendar entry.

The response carries those caveats so the score is never read as compliance
with a real coach or as a medical judgement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, RaceGoal
from app.schemas import (
    AdherenceOverview,
    AdherenceSummaryOut,
    AdherenceWeekOut,
)
from app.services.analysis import (
    RunRecord,
    build_sessions,
    classify_run,
    long_run_target,
    select_phase,
    target_weekly_distance,
    week_start,
)
from app.services.analysis_settings import get_analysis_settings
from app.services.performance import build_overview, ensure_efforts
from app.utils import as_utc, utcnow

MODEL_VERSION = "m10.0"
ALLOWED_WEEKS = (4, 8, 12)


@dataclass
class WeekActual:
    week_start: date
    records: list[RunRecord]
    volume_m: float
    longest_m: float
    quality_sessions: int
    active_days: int
    rest_days: int


def _local_date(value: datetime, offset: timedelta) -> date:
    return (as_utc(value) + offset).date()


def _utc_start(day: date, offset: timedelta) -> datetime:
    return datetime(day.year, day.month, day.day) - offset


def _records(
    db: Session,
    start: date,
    end: date,
    offset: timedelta,
) -> list[RunRecord]:
    margin = timedelta(days=2)
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc >= _utc_start(start, offset) - margin,
            Activity.start_time_utc <= _utc_start(end, offset) + timedelta(days=1) + margin,
        )
        .order_by(Activity.start_time_utc)
    ).all()
    output: list[RunRecord] = []
    for activity in rows:
        local = _local_date(activity.start_time_utc, offset)
        if start <= local <= end and activity.distance_m > 0 and activity.duration_s > 0:
            output.append(
                RunRecord(
                    activity_id=activity.id,
                    start_time_utc=activity.start_time_utc,
                    local_date=local,
                    distance_m=activity.distance_m,
                    duration_s=activity.duration_s,
                    avg_hr=activity.avg_hr,
                    max_hr=activity.max_hr,
                    is_race=activity.is_race,
                    sub_sport=activity.sub_sport,
                    has_streams=activity.has_streams,
                    intensity_override=activity.intensity_override,
                    rpe=activity.rpe,
                )
            )
    return output


def _actual_week(
    records: list[RunRecord],
    monday: date,
    threshold_pace: float | None,
    hr_reference: float | None,
    mode: str = "auto",
    threshold_hr: float | None = None,
) -> WeekActual:
    end = monday + timedelta(days=6)
    week_records = [record for record in records if monday <= record.local_date <= end]
    hard = sum(
        1
        for record in week_records
        if classify_run(
            record,
            threshold_pace,
            hr_reference,
            mode=mode,
            threshold_hr=threshold_hr,
        )
        == "hard"
        and (record.duration_s >= 600 or record.distance_m >= 3000)
    )
    days = {record.local_date for record in week_records}
    return WeekActual(
        week_start=monday,
        records=week_records,
        volume_m=round(sum(record.distance_m for record in week_records), 1),
        longest_m=round(max((record.distance_m for record in week_records), default=0.0), 1),
        quality_sessions=hard,
        active_days=len(days),
        rest_days=7 - len(days),
    )


def _base_weekly(
    records: list[RunRecord],
    monday: date,
) -> float:
    start = monday - timedelta(days=28)
    end = monday - timedelta(days=1)
    total = sum(record.distance_m for record in records if start <= record.local_date <= end)
    return round(total / 4.0, 1)


def _goal_for_week(goals: list[RaceGoal], monday: date) -> RaceGoal | None:
    future = [goal for goal in goals if goal.target_date and goal.target_date >= monday]
    if future:
        return min(future, key=lambda goal: (goal.target_date, goal.distance_m))
    undated = sorted(
        (goal for goal in goals if goal.target_date is None),
        key=lambda goal: goal.distance_m,
    )
    return undated[0] if undated else None


def _last_race(records: list[RunRecord], monday: date) -> date | None:
    races = [
        record.local_date for record in records if record.is_race and record.local_date < monday
    ]
    return max(races, default=None)


def _quality_bounds(phase: str, avoid_quality: bool) -> tuple[int, int]:
    if avoid_quality or phase == "recovery":
        return 0, 0
    if phase == "taper":
        return 1, 1
    if phase == "build":
        return 1, 2
    if phase == "peak":
        return 2, 2
    return 1, 1


def _in_range_status(
    actual: float,
    low: float,
    high: float,
    *,
    tolerance: float = 0.10,
) -> str:
    if high <= 0:
        return "unknown"
    lower = low * (1.0 - tolerance)
    upper = high * (1.0 + tolerance)
    if actual < lower:
        return "under"
    if actual > upper:
        return "over"
    return "within"


def _range_score(actual: float, low: float, high: float) -> float | None:
    if high <= 0:
        return None
    if low <= actual <= high:
        return 100.0
    if actual < low:
        return max(0.0, 100.0 * actual / max(1.0, low))
    return max(0.0, 100.0 - (actual - high) / max(1.0, high) * 100.0)


def _rest_status(actual: int, planned: int) -> str:
    if actual < planned - 1:
        return "under"
    if actual > planned + 1:
        return "over"
    return "within"


def _rest_score(actual: int, planned: int) -> float:
    difference = abs(actual - planned)
    return max(0.0, 100.0 - difference * 25.0)


def _week_out(
    actual: WeekActual,
    *,
    phase: str,
    weekly_low: float,
    weekly_high: float,
    long_low: float,
    long_high: float,
    quality_low: int,
    quality_high: int,
    rest_planned: int,
    sessions_planned: int,
    in_progress: bool,
) -> AdherenceWeekOut:
    volume_status = _in_range_status(actual.volume_m, weekly_low, weekly_high)
    long_status = _in_range_status(actual.longest_m, long_low, long_high)
    quality_status = (
        "unknown"
        if quality_high <= 0
        else "under"
        if actual.quality_sessions < quality_low
        else "over"
        if actual.quality_sessions > quality_high
        else "within"
    )
    rest_status = _rest_status(actual.rest_days, rest_planned)

    components: list[tuple[float, float]] = []
    volume_score = _range_score(actual.volume_m, weekly_low, weekly_high)
    if volume_score is not None:
        components.append((volume_score, 0.45))
    long_score = _range_score(actual.longest_m, long_low, long_high)
    if long_score is not None:
        components.append((long_score, 0.30))
    if quality_high > 0:
        quality_score = min(1.0, actual.quality_sessions / max(1, quality_high)) * 100.0
        components.append((quality_score, 0.15))
    components.append((_rest_score(actual.rest_days, rest_planned), 0.10))

    total_weight = sum(weight for _score, weight in components)
    score = (
        round(sum(value * weight for value, weight in components) / total_weight, 1)
        if total_weight > 0 and not in_progress
        else None
    )

    reasons: list[str] = []
    if actual.volume_m <= 0:
        reasons.append("no_activities")
    if volume_status == "under":
        reasons.append("volume_under")
    elif volume_status == "over":
        reasons.append("volume_over")
    if long_status == "under":
        reasons.append("long_run_under")
    elif long_status == "over":
        reasons.append("long_run_over")
    if quality_status == "under":
        reasons.append("quality_under")
    elif quality_status == "over":
        reasons.append("quality_over")
    if rest_status == "under":
        reasons.append("rest_short")
    elif rest_status == "over":
        reasons.append("rest_extra")
    if in_progress:
        reasons.append("week_in_progress")

    if in_progress:
        status = "in_progress"
    elif actual.volume_m <= 0 or score is None:
        status = "insufficient"
    elif score >= 80:
        status = "ok"
    elif score >= 50:
        status = "partial"
    else:
        status = "low"

    return AdherenceWeekOut(
        week_start=actual.week_start,
        phase=phase,
        status=status,
        score=score,
        volume_actual_m=actual.volume_m,
        volume_low_m=weekly_low,
        volume_high_m=weekly_high,
        volume_status=volume_status,
        longest_actual_m=actual.longest_m,
        long_run_low_m=long_low,
        long_run_high_m=long_high,
        long_run_status=long_status,
        quality_actual=actual.quality_sessions,
        quality_low=quality_low,
        quality_high=quality_high,
        quality_status=quality_status,
        rest_actual=actual.rest_days,
        rest_planned=rest_planned,
        rest_status=rest_status,
        sessions_actual=len(actual.records),
        sessions_planned=sessions_planned,
        active_days=actual.active_days,
        reasons=reasons,
    )


def _ratio(actual: float, low: float, high: float) -> float | None:
    midpoint = (low + high) / 2.0
    if midpoint <= 0:
        return None
    return round(actual / midpoint, 2)


def _summary(items: list[AdherenceWeekOut], current_week: date) -> AdherenceSummaryOut:
    completed = [
        item
        for item in items
        if item.week_start < current_week
        and item.score is not None
        and item.status not in {"in_progress", "insufficient"}
    ]
    scores = [item.score or 0.0 for item in completed]
    average = round(sum(scores) / len(scores), 1) if scores else None
    current = next((item for item in items if item.week_start == current_week), None)
    trend = "unknown"
    if len(scores) >= 4:
        half = len(scores) // 2
        first = sum(scores[:half]) / max(1, half)
        last = sum(scores[-half:]) / max(1, half)
        if last - first >= 5:
            trend = "improving"
        elif last - first <= -5:
            trend = "worsening"
        else:
            trend = "stable"
    elif len(scores) >= 2:
        trend = "stable"

    def average_ratio(attr: str, actual_attr: str, high_attr: str) -> float | None:
        values: list[float] = []
        for item in completed:
            value = _ratio(
                float(getattr(item, actual_attr)),
                float(getattr(item, attr)),
                float(getattr(item, high_attr)),
            )
            if value is not None:
                values.append(value)
        return round(sum(values) / len(values), 2) if values else None

    return AdherenceSummaryOut(
        weeks=len(items),
        scored_weeks=len(completed),
        average_score=average,
        current_score=current.score if current else None,
        trend=trend,
        volume_ratio=average_ratio("volume_low_m", "volume_actual_m", "volume_high_m"),
        long_run_ratio=average_ratio("long_run_low_m", "longest_actual_m", "long_run_high_m"),
        quality_ratio=(
            round(
                sum(item.quality_actual for item in completed)
                / max(1, sum(item.quality_high for item in completed)),
                2,
            )
            if any(item.quality_high > 0 for item in completed)
            else None
        ),
        rest_ratio=(
            round(
                sum(item.rest_actual for item in completed)
                / max(1, sum(item.rest_planned for item in completed)),
                2,
            )
            if completed
            else None
        ),
    )


def build_adherence(
    db: Session,
    weeks: int = 8,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> AdherenceOverview:
    if weeks not in ALLOWED_WEEKS:
        raise ValueError("Unknown adherence window")
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = _local_date(reference, offset)
    current_week = week_start(today)
    first_week = current_week - timedelta(weeks=weeks - 1)
    history_start = first_week - timedelta(days=28)

    ensure_efforts(db)
    overview = build_overview(db, reference)
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold = analysis.threshold_pace_s_per_km
    records = _records(db, history_start, today, offset)
    all_records = _records(db, history_start - timedelta(days=14), today, offset)
    max_hrs = [record.max_hr for record in all_records if record.max_hr]
    avg_hrs = [record.avg_hr for record in all_records if record.avg_hr]
    hr_reference = analysis.max_hr or (
        float(max(max_hrs)) if max_hrs else (max(avg_hrs) * 1.08 if avg_hrs else None)
    )
    goals = list(db.scalars(select(RaceGoal)).all())

    items: list[AdherenceWeekOut] = []
    for index in range(weeks):
        monday = first_week + timedelta(weeks=index)
        actual = _actual_week(
            records,
            monday,
            threshold,
            hr_reference,
            mode=analysis.mode,
            threshold_hr=analysis.threshold_hr,
        )
        base_weekly = _base_weekly(records, monday)
        goal = _goal_for_week(goals, monday)
        last_race = _last_race(all_records, monday)
        phase = select_phase(
            monday,
            goal.target_date if goal else None,
            last_race,
        )
        weekly_low, weekly_high = target_weekly_distance(phase.key, base_weekly)
        long_low, long_high = long_run_target(weekly_low, weekly_high)
        goal_pace = (
            goal.target_time_s / (goal.distance_m / 1000.0)
            if goal is not None and goal.distance_m > 0
            else None
        )
        sessions = build_sessions(
            phase.key,
            weekly_low,
            weekly_high,
            threshold,
            goal_pace,
            avoid_quality=phase.key == "recovery",
        )
        rest_planned = sum(1 for session in sessions if session.type == "rest")
        sessions_planned = len(sessions) - rest_planned
        quality_low, quality_high = _quality_bounds(
            phase.key,
            phase.key == "recovery",
        )
        items.append(
            _week_out(
                actual,
                phase=phase.key,
                weekly_low=weekly_low,
                weekly_high=weekly_high,
                long_low=long_low,
                long_high=long_high,
                quality_low=quality_low,
                quality_high=quality_high,
                rest_planned=rest_planned,
                sessions_planned=sessions_planned,
                in_progress=monday == current_week,
            )
        )

    summary = _summary(items, current_week)
    warnings: list[str] = []
    if not records:
        warnings.append("no_activities")
    if summary.scored_weeks < 2:
        warnings.append("short_history")
    if summary.average_score is None:
        warnings.append("no_completed_weeks")
    if not goals:
        warnings.append("no_goal")
    if any(item.status == "in_progress" for item in items):
        warnings.append("current_week_in_progress")

    status = (
        "insufficient"
        if summary.scored_weeks < 2 or summary.average_score is None
        else "ok"
        if summary.average_score >= 75
        else "partial"
    )
    notes = [
        "suggested_plan_not_registered",
        "adherence_is_heuristic",
        "current_week_excluded",
        "rest_days_derived",
        "classification_uses_current_anchor",
        "not_medical_advice",
    ]
    if analysis.has_manual:
        notes.append("manual_thresholds_applied")

    return AdherenceOverview(
        generated_at=reference,
        model_version=MODEL_VERSION,
        weeks=weeks,
        status=status,
        current_week_start=current_week,
        summary=summary,
        items=items,
        warnings=warnings,
        notes=notes,
    )
