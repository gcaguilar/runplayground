"""Progress views, calendar, reports and race planning (M3).

Everything in this module is derived from activities, best efforts and the
existing prediction models. Nothing is persisted except planned races: a
calendar, a report or a trend can always be rebuilt from the source data, so
there is no second copy of the truth to keep in sync.

Labels are deliberately explicit about provenance:

* measured data comes from :class:`~app.models.Activity`;
* predictions come from the M1 models through ``build_overview``;
* suggested sessions are the M2 training plan spread over the calendar;
* planned races are user input.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, BestEffort, PerformanceSnapshot, PlannedRace, RaceGoal
from app.schemas import (
    CalendarActivePlanOut,
    CalendarDayOut,
    CalendarEntryOut,
    CalendarView,
    CalendarWeekOut,
    ConsistencyOut,
    FitnessPointOut,
    GoalOut,
    GoalProgressOut,
    LoadOut,
    PersonalBestOut,
    PlannedRaceCreate,
    PlannedRaceOut,
    PlannedRaceUpdate,
    ProgressHighlightOut,
    ProgressOverview,
    ProgressTotalsOut,
    ProgressWeekOut,
    ReportNarrativeOut,
    ReportOut,
    SportTotal,
    WeeklyDay,
    WeeklyLoadOut,
)
from app.schemas_plans import RUNNING_SESSION_TYPES as RUNNING_TYPES
from app.services.analysis import (
    RunRecord,
    build_sessions,
    clamp,
    long_run_target,
    select_phase,
    session_load,
    summarize_load,
    target_weekly_distance,
    week_start,
)
from app.services.analysis_settings import get_analysis_settings
from app.services.diagnostics import ACTION_BY_DIMENSION, build_diagnostics
from app.services.performance import build_overview, ensure_efforts, store_snapshot
from app.services.performance_models import (
    STANDARD_DISTANCES,
    riegel_time,
    round_prediction_time,
)
from app.services.plans import (
    get_active_plan,
    plan_sessions_in_range,
)
from app.utils import as_utc, utcnow

MODEL_VERSION = "m3.0"
DEFAULT_WINDOW_DAYS = 180
STANDARD_DISTANCE_TOLERANCE = 0.025
UPCOMING_RACE_LIMIT = 8
REPORT_UPCOMING_DAYS = 56


def _local_date(value: datetime, offset: timedelta) -> date:
    return (as_utc(value) + offset).date()


def _utc_start(day: date, offset: timedelta) -> datetime:
    """Naive UTC instant for 00:00 local time on ``day``."""

    local = datetime(day.year, day.month, day.day)
    return local - offset


def _percent_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _distance_key(distance_m: float) -> str | None:
    for key, standard in STANDARD_DISTANCES:
        if abs(standard - distance_m) / standard <= STANDARD_DISTANCE_TOLERANCE:
            return key
    return None


def _records_for_range(
    db: Session,
    start: date,
    end: date,
    offset: timedelta,
) -> list[RunRecord]:
    """Running records whose *local* date falls inside ``start``..``end``."""

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
    records: list[RunRecord] = []
    for activity in rows:
        local = _local_date(activity.start_time_utc, offset)
        if start <= local <= end and activity.distance_m > 0 and activity.duration_s > 0:
            records.append(
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
    return records


def _activities_for_range(
    db: Session,
    start: date,
    end: date,
    offset: timedelta,
) -> list[Activity]:
    margin = timedelta(days=2)
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.start_time_utc >= _utc_start(start, offset) - margin,
            Activity.start_time_utc <= _utc_start(end, offset) + timedelta(days=1) + margin,
        )
        .order_by(Activity.start_time_utc)
    ).all()
    return [
        activity
        for activity in rows
        if start <= _local_date(activity.start_time_utc, offset) <= end
    ]


def _totals(
    records: list[RunRecord],
    activities: list[Activity],
    threshold_pace: float | None,
    offset: timedelta,
) -> ProgressTotalsOut:
    load = sum(session_load(record, threshold_pace) for record in records)
    elevation = sum(
        float(activity.elevation_gain_m or 0.0)
        for activity in activities
        if activity.sport == "running"
    )
    return ProgressTotalsOut(
        distance_m=round(sum(record.distance_m for record in records), 1),
        duration_s=round(sum(record.duration_s for record in records), 1),
        elevation_gain_m=round(elevation, 1),
        sessions=len(records),
        active_days=len({record.local_date for record in records}),
        load=round(load, 1),
    )


def _delta(
    current: ProgressTotalsOut,
    previous: ProgressTotalsOut,
) -> dict[str, float | None]:
    return {
        "distance_pct": _percent_change(current.distance_m, previous.distance_m),
        "duration_pct": _percent_change(current.duration_s, previous.duration_s),
        "sessions_pct": _percent_change(float(current.sessions), float(previous.sessions)),
        "active_days_pct": _percent_change(float(current.active_days), float(previous.active_days)),
        "load_pct": _percent_change(current.load, previous.load),
    }


def _weekly_series(
    records: list[RunRecord],
    start: date,
    end: date,
    threshold_pace: float | None,
) -> list[ProgressWeekOut]:
    first = week_start(start)
    last = week_start(end)
    buckets: dict[date, ProgressWeekOut] = {}
    current = first
    while current <= last:
        buckets[current] = ProgressWeekOut(
            week_start=current,
            distance_m=0.0,
            duration_s=0.0,
            load=0.0,
            sessions=0,
            active_days=0,
        )
        current += timedelta(days=7)

    days: dict[date, set[date]] = {key: set() for key in buckets}
    for record in records:
        key = week_start(record.local_date)
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket.distance_m += record.distance_m
        bucket.duration_s += record.duration_s
        bucket.load += session_load(record, threshold_pace)
        bucket.sessions += 1
        days[key].add(record.local_date)

    for key, bucket in buckets.items():
        bucket.distance_m = round(bucket.distance_m, 1)
        bucket.duration_s = round(bucket.duration_s, 1)
        bucket.load = round(bucket.load, 1)
        bucket.active_days = len(days[key])
    return list(buckets.values())


def _streaks(run_dates: set[date], today: date) -> tuple[int, int]:
    if not run_dates:
        return 0, 0
    ordered = sorted(run_dates)
    longest = 1
    streak = 1
    for left, right in zip(ordered, ordered[1:], strict=False):
        if (right - left).days == 1:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 1

    cursor = today if today in run_dates else today - timedelta(days=1)
    current = 0
    while cursor in run_dates:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def _consistency(
    records: list[RunRecord],
    weeks: list[ProgressWeekOut],
    window_days: int,
    today: date,
) -> ConsistencyOut:
    run_dates = {record.local_date for record in records}
    current_streak, longest_streak = _streaks(run_dates, today)
    best = max(weeks, key=lambda item: item.distance_m, default=None)
    with_data = [week for week in weeks if week.sessions > 0]
    return ConsistencyOut(
        window_days=window_days,
        weeks=len(weeks),
        weeks_with_data=len(with_data),
        active_days=len(run_dates),
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        weekly_average_m=round(sum(week.distance_m for week in weeks) / max(1, len(weeks)), 1),
        best_week_start=best.week_start if best and best.distance_m > 0 else None,
        best_week_m=best.distance_m if best else 0.0,
    )


def _fitness_series(
    db: Session,
    start: date,
    end: date,
    overview,
) -> list[FitnessPointOut]:
    rows = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= start,
            PerformanceSnapshot.snapshot_date <= end,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    points = [
        FitnessPointOut(
            date=row.snapshot_date,
            time_s=round(row.fitness_anchor_s, 1),
            low_s=round(row.fitness_anchor_low_s, 1)
            if row.fitness_anchor_low_s is not None
            else None,
            high_s=round(row.fitness_anchor_high_s, 1)
            if row.fitness_anchor_high_s is not None
            else None,
            confidence=row.fitness_confidence,
        )
        for row in rows
        if row.fitness_anchor_s is not None
    ]
    anchor = overview.fitness_anchor
    if anchor is not None and (not points or points[-1].date < end):
        points.append(
            FitnessPointOut(
                date=end,
                time_s=round(anchor.time_s, 1),
                low_s=round(anchor.low_s, 1),
                high_s=round(anchor.high_s, 1),
                confidence=anchor.confidence,
            )
        )
    return points


def _best_efforts(db: Session) -> list[PersonalBestOut]:
    rows = db.execute(
        select(BestEffort, Activity)
        .join(Activity, BestEffort.activity_id == Activity.id)
        .where(
            Activity.sport == "running",
            BestEffort.distance_m.in_([distance for _key, distance in STANDARD_DISTANCES]),
        )
        .order_by(BestEffort.distance_m, BestEffort.duration_s)
    ).all()
    best: dict[float, tuple[BestEffort, Activity]] = {}
    for effort, activity in rows:
        bucket = best.get(effort.distance_m)
        if bucket is None or effort.duration_s < bucket[0].duration_s:
            best[effort.distance_m] = (effort, activity)

    output: list[PersonalBestOut] = []
    for key, distance in STANDARD_DISTANCES:
        pair = best.get(distance)
        if pair is None:
            continue
        effort, activity = pair
        output.append(
            PersonalBestOut(
                distance_key=key,
                distance_m=distance,
                time_s=round(effort.duration_s, 1),
                pace_s_per_km=round(effort.duration_s / (distance / 1000.0), 1),
                activity_id=activity.id,
                activity_name=activity.name,
                date=activity.start_time_utc,
                is_race=activity.is_race,
            )
        )
    return output


def _prediction_for_distance(
    distance_m: float, overview
) -> tuple[float | None, float | None, float | None, str | None]:
    for item in overview.distances:
        if (
            abs(item.distance_m - distance_m) / max(1.0, item.distance_m)
            <= STANDARD_DISTANCE_TOLERANCE
            and item.planning is not None
        ):
            return (
                item.planning.time_s,
                item.planning.low_s,
                item.planning.high_s,
                item.confidence,
            )
    anchor = overview.fitness_anchor
    if anchor is None:
        return None, None, None, None
    try:
        time_s = riegel_time(anchor.time_s, anchor.distance_m, distance_m)
        low_s = riegel_time(anchor.low_s, anchor.distance_m, distance_m)
        high_s = riegel_time(anchor.high_s, anchor.distance_m, distance_m)
    except ValueError:
        return None, None, None, None
    return (
        round_prediction_time(time_s),
        round_prediction_time(low_s),
        round_prediction_time(high_s),
        anchor.confidence,
    )


def _goal_progress(
    goals: Iterable[RaceGoal],
    overview,
) -> list[GoalProgressOut]:
    output: list[GoalProgressOut] = []
    for goal in goals:
        predicted, low, high, confidence = _prediction_for_distance(goal.distance_m, overview)
        gap = round(goal.target_time_s - predicted, 1) if predicted is not None else None
        gap_pct = (
            round(gap / max(1.0, predicted) * 100, 1)
            if gap is not None and predicted is not None
            else None
        )
        readiness = (
            round(clamp(goal.target_time_s / predicted * 100.0, 0.0, 100.0), 1)
            if predicted is not None
            else None
        )
        if predicted is None:
            status = "unknown"
        elif predicted <= goal.target_time_s:
            status = "ahead"
        elif predicted <= goal.target_time_s * 1.02:
            status = "close"
        else:
            status = "behind"
        output.append(
            GoalProgressOut(
                distance_key=_distance_key(goal.distance_m),
                distance_m=goal.distance_m,
                target_time_s=goal.target_time_s,
                target_date=goal.target_date,
                race_name=goal.race_name,
                current_time_s=round(predicted, 1) if predicted is not None else None,
                low_s=round(low, 1) if low is not None else None,
                high_s=round(high, 1) if high is not None else None,
                confidence=confidence,
                gap_s=gap,
                gap_pct=gap_pct,
                readiness_pct=readiness,
                status=status,
            )
        )
    return output


def _recent_weekly_distance(db: Session, today: date, offset: timedelta) -> float:
    start = today - timedelta(days=27)
    records = _records_for_range(db, start, today, offset)
    return round(sum(record.distance_m for record in records) / 4.0, 1)


def _race_out(
    race: PlannedRace,
    overview,
    today: date,
    base_weekly_m: float,
) -> PlannedRaceOut:
    days = (race.race_date - today).days
    weeks = int((days + 6) // 7) if days >= 0 else None
    predicted, low, high, confidence = _prediction_for_distance(race.distance_m, overview)
    gap = None
    gap_pct = None
    if predicted is not None and race.goal_time_s:
        gap = round(race.goal_time_s - predicted, 1)
        gap_pct = round(gap / max(1.0, predicted) * 100, 1)

    if predicted is None:
        readiness = "unknown"
    elif race.goal_time_s is None:
        readiness = "no_goal"
    elif predicted <= race.goal_time_s:
        readiness = "ahead"
    elif predicted <= race.goal_time_s * 1.02:
        readiness = "on_track"
    elif predicted <= race.goal_time_s * 1.06:
        readiness = "close"
    else:
        readiness = "behind"

    phase = select_phase(today, race.race_date, None) if days >= 0 else None
    weekly_low = weekly_high = long_low = long_high = None
    if phase is not None:
        weekly_low, weekly_high = target_weekly_distance(phase.key, base_weekly_m)
        long_low, long_high = long_run_target(weekly_low, weekly_high)

    target_pace = None
    target_time = race.goal_time_s or predicted
    if target_time and race.distance_m > 0:
        target_pace = round(target_time / (race.distance_m / 1000.0), 1)

    return PlannedRaceOut(
        id=race.id,
        name=race.name,
        race_date=race.race_date,
        distance_m=race.distance_m,
        goal_time_s=race.goal_time_s,
        priority=race.priority,
        location=race.location,
        notes=race.notes,
        status=race.status,
        activity_id=race.activity_id,
        created_at=race.created_at,
        updated_at=race.updated_at,
        days_to_race=days,
        weeks_to_race=weeks,
        phase=phase.key if phase else None,
        phase_reason=phase.reason if phase else None,
        target_pace_s_per_km=target_pace,
        predicted_time_s=round(predicted, 1) if predicted is not None else None,
        predicted_low_s=round(low, 1) if low is not None else None,
        predicted_high_s=round(high, 1) if high is not None else None,
        prediction_confidence=confidence,
        gap_s=gap,
        gap_pct=gap_pct,
        readiness=readiness,
        weekly_distance_low_m=weekly_low,
        weekly_distance_high_m=weekly_high,
        long_run_low_m=long_low,
        long_run_high_m=long_high,
    )


def _upcoming_races(
    db: Session,
    overview,
    today: date,
    base_weekly_m: float,
    limit: int = UPCOMING_RACE_LIMIT,
) -> list[PlannedRaceOut]:
    races = db.scalars(
        select(PlannedRace)
        .where(
            PlannedRace.status == "planned",
            PlannedRace.race_date >= today,
        )
        .order_by(PlannedRace.race_date, PlannedRace.id)
        .limit(limit)
    ).all()
    return [_race_out(race, overview, today, base_weekly_m) for race in races]


def _highlights(
    activities: list[Activity],
    weeks: list[ProgressWeekOut],
    best_efforts: list[PersonalBestOut],
    offset: timedelta,
) -> list[ProgressHighlightOut]:
    output: list[ProgressHighlightOut] = []
    best_week = max(weeks, key=lambda item: item.distance_m, default=None)
    if best_week is not None and best_week.distance_m > 0:
        output.append(
            ProgressHighlightOut(
                key="biggest_week",
                date=best_week.week_start,
                value=best_week.distance_m,
            )
        )

    running = [activity for activity in activities if activity.sport == "running"]
    longest = max(running, key=lambda item: item.distance_m, default=None)
    if longest is not None and longest.distance_m > 0:
        output.append(
            ProgressHighlightOut(
                key="longest_run",
                date=_local_date(longest.start_time_utc, offset),
                value=round(longest.distance_m, 1),
                activity_id=longest.id,
            )
        )

    climb = max(
        running,
        key=lambda item: float(item.elevation_gain_m or 0.0),
        default=None,
    )
    if climb is not None and float(climb.elevation_gain_m or 0.0) > 0:
        output.append(
            ProgressHighlightOut(
                key="most_elevation",
                date=_local_date(climb.start_time_utc, offset),
                value=round(float(climb.elevation_gain_m or 0.0), 1),
                activity_id=climb.id,
            )
        )

    fastest_5k = next((effort for effort in best_efforts if effort.distance_key == "5k"), None)
    if fastest_5k is not None:
        output.append(
            ProgressHighlightOut(
                key="fastest_5k",
                date=_local_date(fastest_5k.date, offset),
                value=fastest_5k.time_s,
                activity_id=fastest_5k.activity_id,
            )
        )
    return output


def _warnings(
    records: list[RunRecord],
    best_efforts: list[PersonalBestOut],
    goals: list[GoalProgressOut],
    races: list[PlannedRaceOut],
    consistency: ConsistencyOut,
    fitness: list[FitnessPointOut],
) -> list[str]:
    warnings: list[str] = []
    if not records:
        warnings.append("no_running_activities")
    if not best_efforts:
        warnings.append("no_best_efforts")
    if not goals:
        warnings.append("no_goals")
    if not races:
        warnings.append("no_upcoming_races")
    if consistency.weeks_with_data < 4:
        warnings.append("short_history")
    if len(fitness) < 2:
        warnings.append("no_fitness_history")
    return warnings


def build_progress(
    db: Session,
    days: int = DEFAULT_WINDOW_DAYS,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> ProgressOverview:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    days = max(30, min(days, 730))
    today = _local_date(reference, offset)
    start = today - timedelta(days=days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    ensure_efforts(db)
    overview = build_overview(db, reference)
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold = analysis.threshold_pace_s_per_km

    current_records = _records_for_range(db, start, today, offset)
    previous_records = _records_for_range(db, previous_start, previous_end, offset)
    current_activities = _activities_for_range(db, start, today, offset)
    previous_activities = _activities_for_range(db, previous_start, previous_end, offset)

    totals = _totals(current_records, current_activities, threshold, offset)
    previous = _totals(previous_records, previous_activities, threshold, offset)
    weeks = _weekly_series(current_records, start, today, threshold)
    consistency = _consistency(current_records, weeks, days, today)
    fitness = _fitness_series(db, start, today, overview)
    best_efforts = _best_efforts(db)
    goals = _goal_progress(db.scalars(select(RaceGoal).order_by(RaceGoal.distance_m)), overview)
    base_weekly = _recent_weekly_distance(db, today, offset)
    races = _upcoming_races(db, overview, today, base_weekly)
    highlights = _highlights(current_activities, weeks, best_efforts, offset)
    warnings = _warnings(current_records, best_efforts, goals, races, consistency, fitness)

    # Visiting progress is one of the natural daily check-ins in M4. Keep one
    # prediction snapshot per day so tracking has a continuous series even when
    # the performance page is never opened.
    store_snapshot(db, overview)

    status = "ok" if current_records and consistency.weeks_with_data >= 2 else "insufficient"
    return ProgressOverview(
        generated_at=reference,
        window_days=days,
        status=status,
        totals=totals,
        previous=previous,
        delta=_delta(totals, previous),
        consistency=consistency,
        weeks=weeks,
        fitness=fitness,
        best_efforts=best_efforts,
        goals=goals,
        races=races,
        highlights=highlights,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Calendar


def _planned_session_days(
    week_monday: date,
    phase: Any,
    weekly_low_m: float,
    weekly_high_m: float,
    threshold_pace: float | None,
    goal_pace: float | None,
) -> list[tuple[date, Any]]:
    sessions = build_sessions(
        phase.key,
        weekly_low_m,
        weekly_high_m,
        threshold_pace,
        goal_pace,
    )
    output: list[tuple[date, Any]] = []
    for index, session in enumerate(sessions):
        if session.type == "rest":
            continue
        output.append((week_monday + timedelta(days=index), session))
    return output


def build_calendar(
    db: Session,
    start: date,
    weeks: int = 6,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> CalendarView:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = _local_date(reference, offset)
    weeks = max(1, min(weeks, 12))
    grid_start = start - timedelta(days=start.weekday())
    grid_end = grid_start + timedelta(days=weeks * 7 - 1)

    ensure_efforts(db)
    overview = build_overview(db, reference)
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold = analysis.threshold_pace_s_per_km
    records = _records_for_range(db, grid_start - timedelta(days=28), grid_end, offset)
    base_weekly = round(
        sum(
            record.distance_m
            for record in records
            if record.local_date <= today and record.local_date >= today - timedelta(days=27)
        )
        / 4.0,
        1,
    )

    activities = _activities_for_range(db, grid_start, grid_end, offset)
    races = db.scalars(
        select(PlannedRace)
        .where(
            PlannedRace.status != "cancelled",
            PlannedRace.race_date >= grid_start,
            PlannedRace.race_date <= grid_end,
        )
        .order_by(PlannedRace.race_date, PlannedRace.id)
    ).all()
    active_plan = get_active_plan(db)
    registered_sessions = (
        plan_sessions_in_range(active_plan, grid_start, grid_end) if active_plan is not None else []
    )
    registered_by_day: dict[date, list[Any]] = {}
    for session in registered_sessions:
        registered_by_day.setdefault(session.session_date, []).append(session)
    next_race = db.scalar(
        select(PlannedRace)
        .where(
            PlannedRace.status == "planned",
            PlannedRace.race_date >= today,
        )
        .order_by(PlannedRace.race_date, PlannedRace.id)
    )
    goal_pace = None
    if next_race is not None and next_race.goal_time_s and next_race.distance_m > 0:
        goal_pace = next_race.goal_time_s / (next_race.distance_m / 1000.0)

    activities_by_day: dict[date, list[Activity]] = {}
    for activity in activities:
        activities_by_day.setdefault(_local_date(activity.start_time_utc, offset), []).append(
            activity
        )
    races_by_day: dict[date, list[PlannedRace]] = {}
    for race in races:
        races_by_day.setdefault(race.race_date, []).append(race)

    output_weeks: list[CalendarWeekOut] = []
    for week_index in range(weeks):
        week_monday = grid_start + timedelta(weeks=week_index)
        phase = select_phase(
            week_monday,
            next_race.race_date if next_race is not None else None,
            None,
        )
        weekly_low, weekly_high = target_weekly_distance(phase.key, base_weekly)
        sessions = (
            _planned_session_days(
                week_monday,
                phase,
                weekly_low,
                weekly_high,
                threshold,
                goal_pace,
            )
            if records
            else []
        )
        sessions_by_day: dict[date, list[tuple[date, Any]]] = {}
        for session_day, session in sessions:
            if next_race is not None and session_day > next_race.race_date:
                continue
            # Inside the registered plan the suggestion is replaced by the
            # plan's own sessions. Outside it, M3 behaviour is untouched.
            if (
                active_plan is not None
                and active_plan.start_date <= session_day <= active_plan.end_date
            ):
                continue
            sessions_by_day.setdefault(session_day, []).append((session_day, session))

        days: list[CalendarDayOut] = []
        week_actual = 0.0
        for day_index in range(7):
            day = week_monday + timedelta(days=day_index)
            entries: list[CalendarEntryOut] = []
            for race in races_by_day.get(day, []):
                entries.append(
                    CalendarEntryOut(
                        id=f"race:{race.id}",
                        date=day,
                        kind="race",
                        title=race.name,
                        distance_m=race.distance_m,
                        status=race.status,
                        is_race=True,
                        race_id=race.id,
                    )
                )
            for activity in activities_by_day.get(day, []):
                entries.append(
                    CalendarEntryOut(
                        id=f"activity:{activity.id}",
                        date=day,
                        kind="activity",
                        title=activity.name,
                        sport=activity.sport,
                        activity_id=activity.id,
                        distance_m=round(activity.distance_m, 1),
                        duration_s=round(activity.duration_s, 1),
                        status="completed",
                        is_race=activity.is_race,
                    )
                )
            for session in registered_by_day.get(day, []):
                entries.append(
                    CalendarEntryOut(
                        id=f"plan:{session.id}",
                        date=day,
                        kind="plan",
                        title=session.type,
                        distance_m=round(session.distance_m, 1)
                        if session.distance_m is not None
                        else None,
                        duration_s=round(session.duration_s, 1)
                        if session.duration_s is not None
                        else None,
                        intensity=session.intensity,
                        status=session.status,
                        plan_id=active_plan.id if active_plan is not None else None,
                        session_id=session.id,
                        activity_id=session.activity_id,
                    )
                )
            for _session_day, session in sessions_by_day.get(day, []):
                distance = None
                if session.distance_low_m and session.distance_high_m:
                    distance = round((session.distance_low_m + session.distance_high_m) / 2.0, 1)
                duration = None
                if session.duration_low_s and session.duration_high_s:
                    duration = round((session.duration_low_s + session.duration_high_s) / 2.0, 1)
                entries.append(
                    CalendarEntryOut(
                        id=f"session:{day.isoformat()}:{session.type}",
                        date=day,
                        kind="session",
                        title=session.type,
                        distance_m=distance,
                        duration_s=duration,
                        intensity=session.intensity,
                        status="suggested",
                    )
                )

            actual = sum(
                activity.distance_m
                for activity in activities_by_day.get(day, [])
                if activity.sport == "running"
            )
            week_actual += actual
            days.append(
                CalendarDayOut(
                    date=day,
                    entries=entries,
                    actual_distance_m=round(actual, 1),
                    planned_distance_m=round(
                        sum(
                            entry.distance_m or 0.0
                            for entry in entries
                            if entry.kind == "session"
                            or (entry.kind == "plan" and entry.title in RUNNING_TYPES)
                        ),
                        1,
                    ),
                )
            )
        output_weeks.append(
            CalendarWeekOut(
                week_start=week_monday,
                days=days,
                actual_distance_m=round(week_actual, 1),
                planned_distance_m=round(sum(day.planned_distance_m for day in days), 1),
            )
        )

    return CalendarView(
        start=grid_start,
        end=grid_end,
        today=today,
        weeks=output_weeks,
        active_plan=(
            CalendarActivePlanOut(
                id=active_plan.id,
                name=active_plan.name,
                start_date=active_plan.start_date,
                end_date=active_plan.end_date,
                goal_race_id=active_plan.goal_race_id,
                goal_race_name=(
                    active_plan.goal_race.name if active_plan.goal_race is not None else None
                ),
            )
            if active_plan is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Reports


def _load_out(load) -> LoadOut:
    return LoadOut(
        weekly=[
            WeeklyLoadOut(
                week_start=item.week_start,
                distance_m=item.distance_m,
                duration_s=item.duration_s,
                load=item.load,
                sessions=item.sessions,
            )
            for item in load.weekly
        ],
        acute_7d=load.acute_7d,
        chronic_weekly=load.chronic_weekly,
        ratio=load.ratio,
        ramp_pct=load.ramp_pct,
        score=load.score,
        status=load.status,
        reasons=load.reasons,
    )


def _day_series(
    records: list[RunRecord],
    start: date,
    end: date,
) -> list[WeeklyDay]:
    buckets = {
        start + timedelta(days=index): WeeklyDay(
            date=start + timedelta(days=index),
            activities=0,
            distance_m=0.0,
            duration_s=0.0,
        )
        for index in range((end - start).days + 1)
    }
    for record in records:
        day = buckets.get(record.local_date)
        if day is None:
            continue
        day.activities += 1
        day.distance_m += record.distance_m
        day.duration_s += record.duration_s
    for day in buckets.values():
        day.distance_m = round(day.distance_m, 1)
        day.duration_s = round(day.duration_s, 1)
    return list(buckets.values())


def _report_races(
    db: Session,
    overview,
    start: date,
    end: date,
    today: date,
    base_weekly: float,
) -> list[PlannedRaceOut]:
    races = db.scalars(
        select(PlannedRace)
        .where(
            PlannedRace.status != "cancelled",
            PlannedRace.race_date >= start,
            PlannedRace.race_date <= end + timedelta(days=REPORT_UPCOMING_DAYS),
        )
        .order_by(PlannedRace.race_date, PlannedRace.id)
    ).all()
    return [_race_out(race, overview, today, base_weekly) for race in races]


def _report_narrative(
    db: Session,
    start: date,
    end: date,
    totals: ProgressTotalsOut,
    delta: dict[str, float | None],
    diagnostics,
) -> ReportNarrativeOut:
    snapshots = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= start,
            PerformanceSnapshot.snapshot_date <= end,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    points = [
        (snapshot.snapshot_date, snapshot.fitness_anchor_s)
        for snapshot in snapshots
        if snapshot.fitness_anchor_s is not None
    ]
    fitness_change_s = None
    fitness_change_pct = None
    reasons: list[str] = []
    if len(points) >= 2:
        first = float(points[0][1])
        last = float(points[-1][1])
        fitness_change_s = round(first - last, 1)
        fitness_change_pct = round(fitness_change_s / max(1.0, first) * 100.0, 1)
        reasons.append("fitness_from_snapshots")
        if len(points) < 4:
            reasons.append("small_fitness_history")
    else:
        reasons.append("volume_fallback")
        if not points:
            reasons.append("no_fitness_points")

    volume_delta_pct = delta.get("distance_pct")
    improvement: str | None = None
    if fitness_change_pct is not None and fitness_change_pct > 0.5:
        key = "fitness_up"
        tone = "positive"
        improvement = "fitness"
    elif fitness_change_pct is not None and fitness_change_pct < -0.5:
        key = "fitness_down"
        tone = "warning"
    elif volume_delta_pct is not None and volume_delta_pct > 10.0 and totals.sessions > 0:
        key = "volume_up"
        tone = "positive"
        improvement = "volume"
    elif volume_delta_pct is not None and volume_delta_pct < -10.0:
        key = "volume_down"
        tone = "warning"
    elif totals.sessions > 0:
        key = "stable"
        tone = "neutral"
    else:
        key = "insufficient"
        tone = "neutral"
        reasons.append("no_sessions")

    limiter = diagnostics.limiters[0] if diagnostics.limiters else None
    limitation = limiter.dimension_key if limiter else None
    action = (
        ACTION_BY_DIMENSION.get(limitation, "maintain_balance")
        if limitation
        else "maintain_balance"
    )
    if limitation:
        reasons.append("limitation_is_current")
    if improvement is None:
        reasons.append("no_measurable_improvement")

    last_snapshot = next(
        (snapshot for snapshot in reversed(snapshots) if snapshot.fitness_anchor_s is not None),
        None,
    )
    confidence = (
        last_snapshot.fitness_confidence
        if last_snapshot is not None and last_snapshot.fitness_confidence
        else diagnostics.confidence
    )
    evidence: dict[str, float | int | str | None] = {
        "fitness_points": len(points),
        "fitness_start_s": round(float(points[0][1]), 1) if points else None,
        "fitness_end_s": round(float(points[-1][1]), 1) if points else None,
        "volume_delta_pct": volume_delta_pct,
        "sessions": totals.sessions,
        "active_days": totals.active_days,
        "load_ratio": diagnostics.load.ratio,
        "limiter_score": limiter.score if limiter else None,
    }
    return ReportNarrativeOut(
        key=key,
        tone=tone,
        confidence=confidence,
        confidence_score=diagnostics.confidence_score,
        improvement=improvement,
        limitation=limitation,
        action=action,
        fitness_change_s=fitness_change_s,
        fitness_change_pct=fitness_change_pct,
        volume_delta_pct=volume_delta_pct,
        evidence=evidence,
        reasons=reasons,
    )


def build_report(
    db: Session,
    period: str,
    anchor_date: date,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> ReportOut:
    if period not in {"week", "month"}:
        raise ValueError("Unknown report period")
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = _local_date(reference, offset)

    if period == "week":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end = start + timedelta(days=6)
        previous_start = start - timedelta(days=7)
        previous_end = end - timedelta(days=7)
        iso = start.isocalendar()
        label = f"{iso.year}-W{iso.week:02d}"
    else:
        start = anchor_date.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
        previous_end = start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        label = f"{start.year}-{start.month:02d}"

    ensure_efforts(db)
    overview = build_overview(db, reference)
    store_snapshot(db, overview)
    diagnostics = build_diagnostics(db, reference, tz_offset_minutes)
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold = analysis.threshold_pace_s_per_km

    current_records = _records_for_range(db, start, end, offset)
    previous_records = _records_for_range(db, previous_start, previous_end, offset)
    current_activities = _activities_for_range(db, start, end, offset)
    previous_activities = _activities_for_range(db, previous_start, previous_end, offset)
    totals = _totals(current_records, current_activities, threshold, offset)
    previous = _totals(previous_records, previous_activities, threshold, offset)

    weeks = _weekly_series(current_records, start, end, threshold)
    days = _day_series(current_records, start, end)
    # Acute/chronic load needs trailing history, not just the report period:
    # a week report would otherwise look like a spike against itself. For the
    # current period, evaluate as of today so future days do not read as a drop.
    load_reference = min(end, today)
    load_records = _records_for_range(
        db, load_reference - timedelta(days=27), load_reference, offset
    )
    load_summary = summarize_load(load_records, load_reference, threshold)
    base_weekly = _recent_weekly_distance(db, today, offset)
    goals = _goal_progress(db.scalars(select(RaceGoal).order_by(RaceGoal.distance_m)), overview)
    races = _report_races(db, overview, start, end, today, base_weekly)
    highlights = _highlights(current_activities, weeks, _best_efforts(db), offset)

    by_sport: dict[str, SportTotal] = {}
    for activity in current_activities:
        item = by_sport.setdefault(
            activity.sport,
            SportTotal(sport=activity.sport, activities=0, distance_m=0.0, duration_s=0.0),
        )
        item.activities += 1
        item.distance_m = round(item.distance_m + activity.distance_m, 1)
        item.duration_s = round(item.duration_s + activity.duration_s, 1)

    delta = _delta(totals, previous)
    narrative = _report_narrative(db, start, end, totals, delta, diagnostics)

    notes: list[str] = [
        "load_is_estimated",
        "not_medical_advice",
        "narrative_is_derived",
    ]
    if narrative.limitation:
        notes.append("limitation_is_current")
    if previous.sessions == 0:
        notes.append("no_previous_period")
    if any(race.race_date <= end for race in races):
        notes.append("race_in_period")
    if not goals:
        notes.append("goal_missing")
    if totals.sessions == 0:
        notes.append("no_sessions_in_period")

    warnings: list[str] = []
    if not current_records:
        warnings.append("no_running_activities")
    if load_summary.status == "risk":
        warnings.append("load_risk")
    elif load_summary.status == "watch":
        warnings.append("load_attention")

    return ReportOut(
        generated_at=reference,
        period=period,  # type: ignore[arg-type]
        start=start,
        end=end,
        label=label,
        totals=totals,
        previous=previous,
        delta=delta,
        narrative=narrative,
        days=days,
        weeks=weeks,
        by_sport=sorted(by_sport.values(), key=lambda item: item.distance_m, reverse=True),
        load=_load_out(load_summary),
        goals=goals,
        races=races,
        highlights=highlights,
        notes=notes,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Planned races (CRUD)


def list_planned_races(
    db: Session,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> list[PlannedRaceOut]:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = _local_date(reference, offset)
    ensure_efforts(db)
    overview = build_overview(db, reference)
    base_weekly = _recent_weekly_distance(db, today, offset)
    races = db.scalars(
        select(PlannedRace).order_by(PlannedRace.race_date.desc(), PlannedRace.id.desc())
    ).all()
    return [_race_out(race, overview, today, base_weekly) for race in races]


def create_planned_race(db: Session, payload: PlannedRaceCreate) -> PlannedRace:
    race = PlannedRace(
        name=payload.name.strip(),
        race_date=payload.race_date,
        distance_m=float(payload.distance_m),
        goal_time_s=float(payload.goal_time_s) if payload.goal_time_s else None,
        priority=payload.priority,
        location=payload.location.strip() if payload.location else None,
        notes=payload.notes.strip() if payload.notes else None,
        status=payload.status,
        activity_id=payload.activity_id,
    )
    db.add(race)
    db.commit()
    db.refresh(race)
    return race


def update_planned_race(
    db: Session,
    race_id: int,
    payload: PlannedRaceUpdate,
) -> PlannedRace | None:
    race = db.get(PlannedRace, race_id)
    if race is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        race.name = data["name"].strip()
    if "race_date" in data and data["race_date"] is not None:
        race.race_date = data["race_date"]
    if "distance_m" in data and data["distance_m"] is not None:
        race.distance_m = float(data["distance_m"])
    if "goal_time_s" in data:
        race.goal_time_s = float(data["goal_time_s"]) if data["goal_time_s"] else None
    if "priority" in data and data["priority"] is not None:
        race.priority = data["priority"]
    if "location" in data:
        race.location = data["location"].strip() if data["location"] else None
    if "notes" in data:
        race.notes = data["notes"].strip() if data["notes"] else None
    if "status" in data and data["status"] is not None:
        race.status = data["status"]
    if "activity_id" in data:
        race.activity_id = data["activity_id"]
    db.commit()
    db.refresh(race)
    return race


def delete_planned_race(db: Session, race_id: int) -> bool:
    race = db.get(PlannedRace, race_id)
    if race is None:
        return False
    db.delete(race)
    db.commit()
    return True


def race_out(
    db: Session,
    race: PlannedRace,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> PlannedRaceOut:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = _local_date(reference, offset)
    ensure_efforts(db)
    overview = build_overview(db, reference)
    return _race_out(race, overview, today, _recent_weekly_distance(db, today, offset))


def goal_out(goal: RaceGoal) -> GoalOut:
    return GoalOut(
        distance_m=goal.distance_m,
        target_time_s=goal.target_time_s,
        target_date=goal.target_date,
        race_name=goal.race_name,
        notes=goal.notes,
        updated_at=goal.updated_at,
    )


def standard_distance_key(distance_m: float) -> str | None:
    return _distance_key(distance_m)
