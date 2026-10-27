"""Database-backed performance analysis for M1."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    BestEffort,
    ExternalMetric,
    GoalRevision,
    PerformanceSnapshot,
    RaceGoal,
    StreamSample,
)
from app.schemas import (
    DistancePredictionOut,
    EffortOut,
    FitnessAnchorOut,
    GarminMetricPoint,
    GarminRacePrediction,
    GarminReference,
    GoalOut,
    GoalUpsert,
    PerformanceDataSummary,
    PerformanceHistory,
    PerformanceOverview,
    PerformanceSnapshotOut,
    PredictionEstimateOut,
    PreparationSummary,
    SnapshotPredictionOut,
)
from app.services.efforts import SegmentEffort, best_segment, build_points, stream_quality
from app.services.performance_models import (
    LOOKBACK_DAYS,
    MODEL_VERSION,
    RECENT_DAYS,
    STANDARD_DISTANCES,
    Effort,
    ModelEstimate,
    ceiling_estimate,
    confidence_for,
    curve_estimate,
    gap_seconds,
    lookback_cutoff,
    within_race_tolerance,
)
from app.services.state import get_state, set_state
from app.utils import utcnow

PERFORMANCE_STATE_KEY = "performance"
GARMIN_SOURCE = "garmin_export"
GARMIN_METRICS = (
    "vo2max",
    "training_readiness",
    "acute_training_load",
    "chronic_training_load",
    "race_prediction",
)


# ---------------------------------------------------------------------------
# Effort extraction and persistence


def is_predictive_activity(activity: Activity) -> bool:
    if activity.sport != "running":
        return False
    if activity.sub_sport == "trail_running":
        return False
    if activity.distance_m < 1000 or activity.duration_s <= 0:
        return False
    pace = activity.duration_s / (activity.distance_m / 1000.0)
    if pace < 150 or pace > 1200:
        return False
    return activity.start_time_utc <= utcnow() + timedelta(hours=1)


def refresh_activity_efforts(db: Session, activity: Activity) -> int:
    """Replace all best efforts for one activity. The caller commits."""

    db.execute(delete(BestEffort).where(BestEffort.activity_id == activity.id))
    if not is_predictive_activity(activity):
        return 0

    samples = db.execute(
        select(StreamSample.elapsed_s, StreamSample.distance_m)
        .where(StreamSample.activity_id == activity.id)
        .order_by(StreamSample.sample_index)
    ).all()
    points = build_points(
        [row.elapsed_s for row in samples],
        [row.distance_m for row in samples],
    )
    stream_q = (
        stream_quality(
            points,
            has_gps=activity.has_gps,
            has_hr=activity.avg_hr is not None,
            is_full_activity=True,
        )
        if points
        else 0.0
    )

    created = 0
    for _key, target in STANDARD_DISTANCES:
        segment = best_segment(points, target) if points else None
        is_race_distance = within_race_tolerance(activity.distance_m, target)
        method = "stream"
        is_full = False
        quality = stream_q

        if activity.is_race and is_race_distance:
            # The official result, not the GPS segment, is authoritative.
            segment = SegmentEffort(
                distance_m=target,
                duration_s=activity.duration_s,
                start_s=0.0,
                end_s=activity.duration_s,
                method="activity",
            )
            method = "activity"
            is_full = True
            quality = 0.98 if activity.has_gps else 0.92
        elif segment is None and is_race_distance:
            # Short GPS measurement or no stream: fall back to the summary.
            segment = SegmentEffort(
                distance_m=target,
                duration_s=activity.duration_s,
                start_s=0.0,
                end_s=activity.duration_s,
                method="activity",
            )
            method = "activity"
            is_full = True
            quality = 0.62
        elif segment is not None:
            is_full = abs(activity.distance_m - target) <= max(30.0, target * 0.004)
            quality = stream_q + (0.02 if is_full else 0.0)

        if segment is None:
            continue

        db.add(
            BestEffort(
                activity_id=activity.id,
                distance_m=target,
                duration_s=segment.duration_s,
                segment_start_s=segment.start_s,
                segment_end_s=segment.end_s,
                method=method,
                is_full_activity=is_full,
                quality=round(min(0.99, max(0.30, quality)), 2),
            )
        )
        created += 1

    db.flush()
    return created


def refresh_all_efforts(db: Session) -> tuple[int, int]:
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.sport == "running")
            .order_by(Activity.start_time_utc.desc())
        ).all()
    )
    efforts = 0
    for index, activity in enumerate(activities, start=1):
        efforts += refresh_activity_efforts(db, activity)
        if index % 100 == 0:
            db.commit()
    db.commit()
    return len(activities), efforts


def mark_efforts_refreshed(db: Session, activities: int, efforts: int) -> None:
    set_state(
        db,
        PERFORMANCE_STATE_KEY,
        {
            "efforts_version": MODEL_VERSION,
            "efforts_updated_at": utcnow().isoformat(),
            "activities": activities,
            "efforts": efforts,
        },
    )


def ensure_efforts(db: Session) -> None:
    state = get_state(db, PERFORMANCE_STATE_KEY, {})
    if state.get("efforts_version") == MODEL_VERSION:
        return
    running = db.scalar(select(func.count(Activity.id)).where(Activity.sport == "running")) or 0
    if running == 0:
        mark_efforts_refreshed(db, 0, 0)
        db.commit()
        return
    activities, efforts = refresh_all_efforts(db)
    mark_efforts_refreshed(db, activities, efforts)
    db.commit()


def load_efforts(db: Session, now: datetime | None = None) -> list[Effort]:
    reference = now or utcnow()
    rows = (
        db.execute(
            select(BestEffort)
            .join(BestEffort.activity)
            .where(
                Activity.sport == "running",
                Activity.start_time_utc >= lookback_cutoff(reference),
                Activity.start_time_utc <= reference + timedelta(hours=1),
                BestEffort.duration_s > 0,
            )
            .order_by(BestEffort.distance_m, BestEffort.duration_s)
        )
        .unique()
        .scalars()
        .all()
    )
    output: list[Effort] = []
    for row in rows:
        activity = row.activity
        if activity is None or activity.sub_sport == "trail_running":
            continue
        pace = row.duration_s / (row.distance_m / 1000.0)
        if pace < 150 or pace > 1200:
            continue
        output.append(
            Effort(
                activity_id=activity.id,
                activity_name=activity.name,
                start_time_utc=activity.start_time_utc,
                distance_m=row.distance_m,
                duration_s=row.duration_s,
                method=row.method,
                is_full_activity=row.is_full_activity,
                is_race=activity.is_race,
                has_gps=activity.has_gps,
                quality=row.quality,
                segment_start_s=row.segment_start_s,
                segment_end_s=row.segment_end_s,
            )
        )
    return output


# ---------------------------------------------------------------------------
# Overview


def build_overview(db: Session, now: datetime | None = None) -> PerformanceOverview:
    reference = now or utcnow()
    efforts = load_efforts(db, reference)
    official = _official_prs(db, reference)
    goals = {goal.distance_m: goal for goal in db.scalars(select(RaceGoal)).all()}
    preparation = _preparation(db, reference)
    data = _data_summary(db, efforts, preparation, reference)
    garmin = _garmin_reference(db)

    distances: list[DistancePredictionOut] = []
    for key, target in STANDARD_DISTANCES:
        ceiling = ceiling_estimate(efforts, target, reference)
        planning = curve_estimate(efforts, target, reference)
        recent = _recent_best(efforts, target, reference)
        official_pr = official.get(key)
        goal = goals.get(target)
        has_race = official_pr is not None
        confidence = confidence_for(
            ceiling,
            planning,
            efforts,
            target,
            longest_run_m=preparation.longest_run_90d_m,
            has_race_at_distance=has_race,
            now=reference,
        )
        gap_s, gap_pct = gap_seconds(ceiling, planning)
        goal_gap_s = None
        goal_gap_pct = None
        if goal is not None and planning is not None:
            goal_gap_s = round(goal.target_time_s - planning.time_s, 1)
            goal_gap_pct = round(goal_gap_s / max(1.0, planning.time_s) * 100, 1)
        status = "ok" if ceiling is not None and planning is not None else "insufficient"
        distances.append(
            DistancePredictionOut(
                distance_key=key,
                distance_m=target,
                status=status,
                official_pr=_effort_out(official_pr) if official_pr else None,
                recent_best=_effort_out(recent) if recent else None,
                goal=_goal_out(goal) if goal else None,
                ceiling=_estimate_out(ceiling, target),
                planning=_estimate_out(planning, target),
                gap_s=gap_s,
                gap_pct=gap_pct,
                goal_gap_s=goal_gap_s,
                goal_gap_pct=goal_gap_pct,
                confidence=confidence.label,
                confidence_score=confidence.score,
                confidence_reasons=confidence.reasons,
                inputs={
                    "effort_count": len(efforts),
                    "recent_effort_count": sum(
                        1
                        for effort in efforts
                        if effort.start_time_utc >= reference - timedelta(days=RECENT_DAYS)
                    ),
                    "races_at_distance": 1 if has_race else 0,
                },
            )
        )

    anchor_distance = next(
        (item for item in distances if item.distance_key == "10k"),
        None,
    )
    anchor = None
    if anchor_distance is not None and anchor_distance.planning is not None:
        anchor = FitnessAnchorOut(
            distance_m=anchor_distance.distance_m,
            time_s=anchor_distance.planning.time_s,
            low_s=anchor_distance.planning.low_s,
            high_s=anchor_distance.planning.high_s,
            pace_s_per_km=anchor_distance.planning.pace_s_per_km,
            confidence=anchor_distance.confidence,
            confidence_score=anchor_distance.confidence_score,
            as_of=reference,
        )

    status = "ok" if anchor is not None else "insufficient"
    if anchor is not None and sum(1 for item in distances if item.planning is not None) < len(
        distances
    ):
        status = "partial"

    return PerformanceOverview(
        generated_at=reference,
        model_version=MODEL_VERSION,
        window_days=LOOKBACK_DAYS,
        recent_days=RECENT_DAYS,
        status=status,
        fitness_anchor=anchor,
        distances=distances,
        data=data,
        preparation=preparation,
        garmin=garmin,
        warnings=_warnings(db, efforts, official, goals, garmin, reference),
    )


def store_snapshot(db: Session, overview: PerformanceOverview) -> None:
    snapshot_date = overview.generated_at.date()
    snapshot = db.scalar(
        select(PerformanceSnapshot).where(PerformanceSnapshot.snapshot_date == snapshot_date)
    )
    predictions = [
        SnapshotPredictionOut(
            distance_key=item.distance_key,
            distance_m=item.distance_m,
            planning_s=item.planning.time_s if item.planning else None,
            planning_low_s=item.planning.low_s if item.planning else None,
            planning_high_s=item.planning.high_s if item.planning else None,
            confidence=item.confidence if item.planning else None,
        ).model_dump(mode="json")
        for item in overview.distances
    ]
    if snapshot is None:
        snapshot = PerformanceSnapshot(
            snapshot_date=snapshot_date,
            computed_at=overview.generated_at,
            model_version=overview.model_version,
            predictions=predictions,
            summary={},
        )
        db.add(snapshot)
    snapshot.computed_at = overview.generated_at
    snapshot.model_version = overview.model_version
    snapshot.fitness_anchor_s = overview.fitness_anchor.time_s if overview.fitness_anchor else None
    snapshot.fitness_anchor_low_s = (
        overview.fitness_anchor.low_s if overview.fitness_anchor else None
    )
    snapshot.fitness_anchor_high_s = (
        overview.fitness_anchor.high_s if overview.fitness_anchor else None
    )
    snapshot.fitness_confidence = (
        overview.fitness_anchor.confidence if overview.fitness_anchor else None
    )
    snapshot.predictions = predictions
    snapshot.summary = {
        "status": overview.status,
        "efforts": overview.data.efforts,
        "races": overview.data.races,
        "warnings": overview.warnings,
    }
    db.commit()


def get_history(db: Session, days: int = 180) -> PerformanceHistory:
    cutoff = utcnow().date() - timedelta(days=max(1, days))
    rows = db.scalars(
        select(PerformanceSnapshot)
        .where(PerformanceSnapshot.snapshot_date >= cutoff)
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    items = []
    for row in rows:
        try:
            predictions = [SnapshotPredictionOut.model_validate(item) for item in row.predictions]
        except Exception:  # noqa: BLE001 - old/corrupt snapshot should not break the page
            predictions = []
        items.append(
            PerformanceSnapshotOut(
                date=row.snapshot_date,
                computed_at=row.computed_at,
                fitness_anchor_s=row.fitness_anchor_s,
                fitness_anchor_low_s=row.fitness_anchor_low_s,
                fitness_anchor_high_s=row.fitness_anchor_high_s,
                fitness_confidence=row.fitness_confidence,
                predictions=predictions,
            )
        )
    return PerformanceHistory(items=items, days=days)


# ---------------------------------------------------------------------------
# Goals


def get_goal(db: Session, distance_m: float) -> RaceGoal | None:
    return db.scalar(select(RaceGoal).where(RaceGoal.distance_m == distance_m))


def list_goals(db: Session) -> list[GoalOut]:
    return [_goal_out(goal) for goal in db.scalars(select(RaceGoal).order_by(RaceGoal.distance_m))]


def upsert_goal(db: Session, distance_m: float, payload: GoalUpsert) -> GoalOut:
    goal = get_goal(db, distance_m)
    if goal is None:
        goal = RaceGoal(distance_m=distance_m)
        db.add(goal)
    goal.target_time_s = float(payload.target_time_s)
    goal.target_date = payload.target_date
    goal.race_name = payload.race_name.strip() if payload.race_name else None
    goal.notes = payload.notes.strip() if payload.notes else None
    db.commit()
    db.refresh(goal)
    _record_goal_revision(db, goal)
    return _goal_out(goal)


def _record_goal_revision(db: Session, goal: RaceGoal) -> None:
    """Append a revision only when the target itself changed.

    Notes alone are not a target change; re-saving the same goal should not fill
    the history with duplicate rows.
    """

    latest = db.scalar(
        select(GoalRevision)
        .where(GoalRevision.distance_m == goal.distance_m)
        .order_by(GoalRevision.created_at.desc(), GoalRevision.id.desc())
    )
    if (
        latest is not None
        and abs(latest.target_time_s - goal.target_time_s) < 0.5
        and latest.target_date == goal.target_date
        and (latest.race_name or None) == (goal.race_name or None)
    ):
        return

    overview = build_overview(db)
    planning = next(
        (
            item.planning
            for item in overview.distances
            if abs(item.distance_m - goal.distance_m) / max(1.0, item.distance_m) <= 0.025
        ),
        None,
    )
    db.add(
        GoalRevision(
            distance_m=goal.distance_m,
            target_time_s=goal.target_time_s,
            target_date=goal.target_date,
            race_name=goal.race_name,
            notes=goal.notes,
            prediction_time_s=planning.time_s if planning else None,
            prediction_low_s=planning.low_s if planning else None,
            prediction_high_s=planning.high_s if planning else None,
            confidence=next(
                (
                    item.confidence
                    for item in overview.distances
                    if abs(item.distance_m - goal.distance_m) / max(1.0, item.distance_m) <= 0.025
                ),
                None,
            ),
        )
    )
    db.commit()


def delete_goal(db: Session, distance_m: float) -> bool:
    goal = get_goal(db, distance_m)
    if goal is None:
        return False
    db.delete(goal)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Helpers


def _official_prs(db: Session, now: datetime) -> dict[str, Effort]:
    activities = db.scalars(
        select(Activity)
        .where(
            Activity.sport == "running",
            Activity.is_race.is_(True),
            Activity.duration_s > 0,
            Activity.start_time_utc <= now + timedelta(hours=1),
        )
        .order_by(Activity.duration_s)
    ).all()
    output: dict[str, Effort] = {}
    for activity in activities:
        if activity.sub_sport == "trail_running":
            continue
        for key, target in STANDARD_DISTANCES:
            if key in output:
                continue
            if not within_race_tolerance(activity.distance_m, target):
                continue
            output[key] = Effort(
                activity_id=activity.id,
                activity_name=activity.name,
                start_time_utc=activity.start_time_utc,
                distance_m=target,
                duration_s=activity.duration_s,
                method="race",
                is_full_activity=True,
                is_race=True,
                has_gps=activity.has_gps,
                quality=1.0,
                segment_start_s=0.0,
                segment_end_s=activity.duration_s,
            )
    return output


def _recent_best(efforts: list[Effort], target: float, now: datetime) -> Effort | None:
    candidates = [
        effort
        for effort in efforts
        if effort.distance_m == target
        and effort.start_time_utc >= now - timedelta(days=RECENT_DAYS)
    ]
    return min(candidates, key=lambda effort: effort.duration_s, default=None)


def _preparation(db: Session, now: datetime) -> PreparationSummary:
    longest = db.scalar(
        select(func.max(Activity.distance_m)).where(
            Activity.sport == "running",
            Activity.start_time_utc >= now - timedelta(days=90),
        )
    )
    distance_28 = db.scalar(
        select(func.sum(Activity.distance_m)).where(
            Activity.sport == "running",
            Activity.start_time_utc >= now - timedelta(days=28),
        )
    )
    races = db.scalar(
        select(func.count(Activity.id)).where(
            Activity.sport == "running",
            Activity.is_race.is_(True),
            Activity.start_time_utc >= now - timedelta(days=RECENT_DAYS),
        )
    )
    efforts_365 = db.scalar(
        select(func.count(BestEffort.id))
        .join(BestEffort.activity)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc >= now - timedelta(days=RECENT_DAYS),
        )
    )
    return PreparationSummary(
        longest_run_90d_m=round(float(longest), 1) if longest else None,
        weekly_distance_28d_m=round(float(distance_28) / 4.0, 1) if distance_28 else None,
        races_365d=int(races or 0),
        efforts_365d=int(efforts_365 or 0),
    )


def _data_summary(
    db: Session,
    efforts: list[Effort],
    preparation: PreparationSummary,
    now: datetime,
) -> PerformanceDataSummary:
    running = db.scalar(
        select(func.count(Activity.id)).where(
            Activity.sport == "running",
            Activity.start_time_utc >= now - timedelta(days=LOOKBACK_DAYS),
        )
    )
    with_streams = db.scalar(
        select(func.count(Activity.id)).where(
            Activity.sport == "running",
            Activity.has_streams.is_(True),
            Activity.start_time_utc >= now - timedelta(days=LOOKBACK_DAYS),
        )
    )
    return PerformanceDataSummary(
        running_activities=int(running or 0),
        activities_with_streams=int(with_streams or 0),
        efforts=len(efforts),
        races=preparation.races_365d,
        first_effort_at=min((effort.start_time_utc for effort in efforts), default=None),
        last_effort_at=max((effort.start_time_utc for effort in efforts), default=None),
    )


def _garmin_reference(db: Session) -> GarminReference:
    rows = db.scalars(
        select(ExternalMetric)
        .where(ExternalMetric.source == GARMIN_SOURCE)
        .order_by(ExternalMetric.metric_date.desc())
    ).all()
    if not rows:
        return GarminReference()

    imported_at = max(row.imported_at for row in rows)
    vo2max_points = [
        GarminMetricPoint(date=row.metric_date, value=row.value)
        for row in sorted(
            (row for row in rows if row.metric == "vo2max"),
            key=lambda row: row.metric_date,
        )
    ]
    race_predictions: dict[float, ExternalMetric] = {}
    for row in rows:
        if row.metric == "race_prediction" and row.distance_m not in race_predictions:
            race_predictions[row.distance_m] = row

    def latest(metric: str) -> GarminMetricPoint | None:
        row = next((item for item in rows if item.metric == metric), None)
        return GarminMetricPoint(date=row.metric_date, value=row.value) if row else None

    return GarminReference(
        imported_at=imported_at,
        vo2max=latest("vo2max"),
        vo2max_series=vo2max_points[-180:],
        readiness=latest("training_readiness"),
        acute_training_load=latest("acute_training_load"),
        chronic_training_load=latest("chronic_training_load"),
        race_predictions=[
            GarminRacePrediction(
                date=row.metric_date,
                distance_m=row.distance_m,
                time_s=row.value,
            )
            for row in sorted(race_predictions.values(), key=lambda item: item.distance_m)
        ],
    )


def garmin_reference(db: Session) -> GarminReference:
    return _garmin_reference(db)


def _warnings(
    db: Session,
    efforts: list[Effort],
    official: dict[str, Effort],
    goals: dict[str, RaceGoal],
    garmin: GarminReference,
    now: datetime,
) -> list[str]:
    warnings: list[str] = []
    activities = db.scalar(select(func.count(Activity.id))) or 0
    running = db.scalar(select(func.count(Activity.id)).where(Activity.sport == "running")) or 0
    streams = (
        db.scalar(
            select(func.count(Activity.id)).where(
                Activity.sport == "running",
                Activity.has_streams.is_(True),
            )
        )
        or 0
    )
    if activities == 0:
        warnings.append("no_activities")
    if running == 0:
        warnings.append("no_running_activities")
    elif streams == 0:
        warnings.append("no_streams")
    if not efforts:
        warnings.append("no_efforts")
    elif len(efforts) < 3:
        warnings.append("few_efforts")
    if not official:
        warnings.append("no_races")
    if not goals:
        warnings.append("no_goals")
    if garmin.imported_at is None:
        warnings.append("no_garmin_export")
    elif garmin.imported_at < now - timedelta(days=90):
        warnings.append("garmin_export_stale")
    if efforts:
        newest = max(effort.start_time_utc for effort in efforts)
        if newest < now - timedelta(days=RECENT_DAYS):
            warnings.append("stale_efforts")
    return warnings


def _estimate_out(
    estimate: ModelEstimate | None, target_distance_m: float
) -> PredictionEstimateOut | None:
    if estimate is None:
        return None
    pace = estimate.time_s / (target_distance_m / 1000.0)
    return PredictionEstimateOut(
        time_s=estimate.time_s,
        low_s=estimate.low_s,
        high_s=estimate.high_s,
        pace_s_per_km=round(pace, 1),
        method=estimate.method,
        sigma=round(estimate.sigma, 4),
        source_efforts=[_effort_out(effort) for effort in estimate.source_efforts],
        detail=estimate.detail,
    )


def _effort_out(effort: Effort) -> EffortOut:
    return EffortOut(
        activity_id=effort.activity_id,
        activity_name=effort.activity_name,
        start_time_utc=effort.start_time_utc,
        distance_m=effort.distance_m,
        duration_s=round(effort.duration_s, 1),
        pace_s_per_km=round(effort.pace_s_per_km, 1),
        method=effort.method,
        is_full_activity=effort.is_full_activity,
        is_race=effort.is_race,
        has_gps=effort.has_gps,
        quality=round(effort.quality, 2),
        segment_start_s=effort.segment_start_s,
        segment_end_s=effort.segment_end_s,
    )


def _goal_out(goal: RaceGoal) -> GoalOut:
    return GoalOut(
        distance_m=goal.distance_m,
        target_time_s=goal.target_time_s,
        target_date=goal.target_date,
        race_name=goal.race_name,
        notes=goal.notes,
        updated_at=goal.updated_at,
    )
