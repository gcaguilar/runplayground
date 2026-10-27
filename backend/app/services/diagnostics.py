"""Database-backed diagnostics and weekly training plan (M2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, BestEffort, ExternalMetric, RaceGoal
from app.schemas import (
    AnalysisCoverageOut,
    AnalysisReferenceOut,
    DiagnosticsOverview,
    DimensionOut,
    GoalOut,
    IntensityBucketOut,
    IntensityOut,
    IntensityTargetOut,
    LimiterOut,
    LoadOut,
    TrainingFocusOut,
    TrainingLoadTargetOut,
    TrainingPlan,
    TrainingSessionOut,
    WeeklyLoadOut,
)
from app.services.analysis import (
    BASELINE_DAYS,
    DIMENSION_WEIGHTS,
    INTENSITY_TARGETS,
    MODEL_VERSION,
    WEEKS_IN_WINDOW,
    WINDOW_DAYS,
    LoadSummary,
    Phase,
    RunRecord,
    build_sessions,
    clamp,
    confidence_label,
    long_run_target,
    select_phase,
    status_for,
    summarize_consistency,
    summarize_intensity,
    summarize_load,
    summarize_recovery,
    summarize_specificity,
    summarize_volume,
    target_weekly_distance,
    week_start,
)
from app.services.analysis_settings import get_analysis_settings
from app.services.performance import build_overview, garmin_reference
from app.utils import as_utc, utcnow

ACTION_BY_DIMENSION = {
    "volume": "increase_volume",
    "consistency": "build_consistency",
    "intensity": "polarize_intensity",
    "load": "stabilize_load",
    "recovery": "prioritize_recovery",
    "specificity": "add_specific_work",
}


def build_diagnostics(
    db: Session,
    now: datetime | None = None,
    tz_offset_minutes: int = 0,
) -> DiagnosticsOverview:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()
    query_start = reference - timedelta(days=WINDOW_DAYS + BASELINE_DAYS)

    activities = db.scalars(
        select(Activity)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc >= query_start,
            Activity.start_time_utc <= reference,
        )
        .order_by(Activity.start_time_utc)
    ).all()
    records = [
        _record(activity, offset)
        for activity in activities
        if activity.distance_m > 0 and activity.duration_s > 0
    ]
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    window = [record for record in records if record.local_date >= window_start]

    overview = build_overview(db, reference)
    anchor = overview.fitness_anchor
    observed_pace = anchor.pace_s_per_km if anchor else None
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold_pace = analysis.threshold_pace_s_per_km
    hr_reference = analysis.max_hr or _hr_reference(window)
    threshold_hr = analysis.threshold_hr
    classification_mode = analysis.mode
    goal = _select_goal(db.scalars(select(RaceGoal)).all(), today)
    has_goal_effort = _has_goal_effort(db, goal, reference)
    readiness_values, readiness_average = _readiness(db, today)
    garmin = garmin_reference(db)

    volume = summarize_volume(records, today)
    consistency = summarize_consistency(records, today)
    intensity = summarize_intensity(
        window,
        threshold_pace,
        hr_reference,
        mode=classification_mode,
        threshold_hr=threshold_hr,
    )
    load = summarize_load(records, today, threshold_pace)
    recovery = summarize_recovery(
        records,
        today,
        threshold_pace,
        hr_reference,
        readiness_average,
        mode=classification_mode,
        threshold_hr=threshold_hr,
    )
    specificity = summarize_specificity(
        records,
        today,
        goal.distance_m if goal else None,
        has_goal_effort,
        threshold_pace,
        hr_reference,
        mode=classification_mode,
        threshold_hr=threshold_hr,
    )

    week_starts = {week_start(record.local_date) for record in window}
    coverage_confidence = _coverage_confidence(window, week_starts)
    dimensions = [
        _dimension(
            "volume",
            volume.score,
            volume.reasons,
            {
                "weekly_avg_m": volume.weekly_avg_m,
                "recent_28_m": volume.recent_28_m,
                "trend_pct": volume.trend_pct,
                "longest_28_m": volume.longest_28_m,
            },
            coverage_confidence,
        ),
        _dimension(
            "consistency",
            consistency.score,
            consistency.reasons,
            {
                "active_weeks": consistency.active_weeks,
                "weeks": consistency.weeks,
                "runs_per_week": consistency.runs_per_week,
                "longest_gap_days": consistency.longest_gap_days,
            },
            coverage_confidence,
        ),
        _dimension(
            "intensity",
            intensity.score,
            intensity.reasons,
            {
                "easy_share": intensity.buckets[0].share,
                "moderate_share": intensity.buckets[1].share,
                "hard_share": intensity.buckets[2].share,
                "classified_sessions": intensity.classified_sessions,
            },
            coverage_confidence * (1.0 if threshold_pace else 0.75 if hr_reference else 0.45),
        ),
        _dimension(
            "load",
            load.score,
            load.reasons,
            {
                "acute_7d": load.acute_7d,
                "chronic_weekly": load.chronic_weekly,
                "ratio": load.ratio,
                "ramp_pct": load.ramp_pct,
            },
            coverage_confidence * (1.0 if threshold_pace else 0.82),
        ),
        _dimension(
            "recovery",
            recovery.score,
            recovery.reasons,
            {
                "rest_days_per_week": recovery.rest_days_per_week,
                "back_to_back_hard": recovery.back_to_back_hard,
                "longest_streak": recovery.longest_streak,
                "readiness": recovery.readiness,
            },
            min(1.0, coverage_confidence + (0.12 if readiness_average is not None else 0.0)),
        ),
        _dimension(
            "specificity",
            specificity.score,
            specificity.reasons,
            {
                "longest_28_m": specificity.longest_28_m,
                "target_long_m": specificity.target_long_m,
                "hard_sessions": specificity.hard_sessions,
                "long_runs": specificity.long_runs,
            },
            coverage_confidence * (1.0 if threshold_pace else 0.78),
        ),
    ]

    known = [dimension for dimension in dimensions if dimension.score is not None]
    overall_score: float | None
    if len(known) < 3:
        overall_score = None
        overall_status = "insufficient"
    else:
        total_weight = sum(DIMENSION_WEIGHTS[dimension.key] for dimension in known)
        overall_score = round(
            sum((dimension.score or 0.0) * DIMENSION_WEIGHTS[dimension.key] for dimension in known)
            / total_weight,
            1,
        )
        overall_status = status_for(overall_score)

    limiters = _limiters(dimensions)
    if overall_status == "insufficient":
        headline = "insufficient"
    elif limiters:
        headline = limiters[0].dimension_key
    else:
        headline = "balanced"

    confidence_score = coverage_confidence
    if threshold_pace:
        confidence_score += 0.05
    if readiness_average is not None:
        confidence_score += 0.04
    if len(known) >= 5:
        confidence_score += 0.04
    confidence_score = round(clamp(confidence_score, 0.08, 0.95), 2)

    last_activity = max((record.start_time_utc for record in window), default=None)
    last_race = max((record.start_time_utc for record in records if record.is_race), default=None)
    trail_share = (
        sum(record.duration_s for record in window if record.is_trail)
        / sum(record.duration_s for record in window)
        if window
        else 0.0
    )

    warnings: list[str] = []
    if not window:
        warnings.append("no_activities")
    elif len(window) < 6:
        warnings.append("few_activities")
    if observed_pace is None:
        warnings.append("no_anchor")
    if not any(record.avg_hr for record in window):
        warnings.append("no_hr")
    if goal is None:
        warnings.append("no_goal")
    if readiness_average is None:
        warnings.append("no_readiness")
    if len(week_starts) < 4:
        warnings.append("short_history")
    if last_activity is not None and (today - (as_utc(last_activity) + offset).date()).days > 14:
        warnings.append("stale_data")
    if trail_share > 0.4:
        warnings.append("trail_heavy")

    return DiagnosticsOverview(
        generated_at=reference,
        model_version=MODEL_VERSION,
        window_days=WINDOW_DAYS,
        status=overall_status,
        score=overall_score,
        headline=headline,
        confidence=confidence_label(confidence_score),
        confidence_score=confidence_score,
        goal=_goal_out(goal) if goal else None,
        dimensions=dimensions,
        limiters=limiters,
        intensity=_intensity_out(intensity),
        load=_load_out(load),
        coverage=AnalysisCoverageOut(
            activities=len(window),
            weeks_with_data=len(week_starts),
            window_weeks=WEEKS_IN_WINDOW,
            first_activity_at=min(
                (record.start_time_utc for record in window),
                default=None,
            ),
            last_activity_at=last_activity,
            last_race_at=last_race,
            has_anchor=observed_pace is not None,
            anchor_pace_s_per_km=round(observed_pace, 1) if observed_pace else None,
            has_hr=any(record.avg_hr for record in window),
            trail_share=round(trail_share, 3),
            readiness_days=len(readiness_values),
        ),
        reference=AnalysisReferenceOut(
            imported_at=garmin.imported_at,
            readiness_28d=readiness_average,
            acute_load=garmin.acute_training_load.value if garmin.acute_training_load else None,
            chronic_load=garmin.chronic_training_load.value
            if garmin.chronic_training_load
            else None,
        ),
        warnings=warnings,
    )


def build_training_plan(
    db: Session,
    now: datetime | None = None,
    tz_offset_minutes: int = 0,
) -> TrainingPlan:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()
    diagnostics = build_diagnostics(db, reference, tz_offset_minutes)

    goal = diagnostics.goal
    last_race_date = (
        (as_utc(diagnostics.coverage.last_race_at) + offset).date()
        if diagnostics.coverage.last_race_at
        else None
    )
    phase = select_phase(today, goal.target_date if goal else None, last_race_date)

    analysis = get_analysis_settings(db, reference)
    session_threshold = (
        analysis.threshold_pace_s_per_km or diagnostics.coverage.anchor_pace_s_per_km
    )
    base_weekly = _metric(diagnostics, "volume", "weekly_avg_m") or 0.0
    load_ratio = diagnostics.load.ratio
    limiter_keys = {limiter.dimension_key for limiter in diagnostics.limiters}
    reduce_for_load = "load" in limiter_keys or (load_ratio is not None and load_ratio > 1.30)
    avoid_quality = (
        phase.key == "recovery"
        or diagnostics.load.status == "risk"
        or _dimension_status(diagnostics, "recovery") == "risk"
    )

    weekly_low, weekly_high = target_weekly_distance(
        phase.key,
        base_weekly,
        reduce_for_load=reduce_for_load,
    )
    goal_pace = (
        goal.target_time_s / (goal.distance_m / 1000.0) if goal and goal.distance_m > 0 else None
    )
    sessions = (
        build_sessions(
            phase.key,
            weekly_low,
            weekly_high,
            session_threshold,
            goal_pace,
            avoid_quality=avoid_quality,
        )
        if diagnostics.status != "insufficient"
        else []
    )

    focus = _focus(diagnostics)
    long_low, long_high = long_run_target(weekly_low, weekly_high)
    quality_low, quality_high = _quality_target(phase, avoid_quality)

    notes: list[str] = ["intensity_from_pace", "load_is_estimated", "not_medical_advice"]
    if diagnostics.reference.readiness_28d is not None:
        notes.append("readiness_reference_only")
    if goal is None:
        notes.append("goal_missing")
    elif goal.target_date is None:
        notes.append("goal_without_date")
    if diagnostics.status == "insufficient":
        notes.append("insufficient_data")
    if analysis.has_manual:
        notes.append("manual_thresholds_applied")
    if analysis.mode != "auto":
        notes.append(f"classification_mode_{analysis.mode}")

    return TrainingPlan(
        generated_at=reference,
        model_version=MODEL_VERSION,
        status=diagnostics.status,
        phase=phase.key,
        phase_reason=phase.reason,
        weeks_to_goal=phase.weeks_to_goal,
        goal=goal,
        confidence=diagnostics.confidence,
        confidence_score=diagnostics.confidence_score,
        focus=focus,
        sessions=[
            TrainingSessionOut(
                type=session.type,
                intensity=session.intensity,
                priority=session.priority,
                duration_low_s=session.duration_low_s,
                duration_high_s=session.duration_high_s,
                distance_low_m=session.distance_low_m,
                distance_high_m=session.distance_high_m,
                purpose=session.purpose,
            )
            for session in sessions
        ],
        load_target=TrainingLoadTargetOut(
            weekly_distance_low_m=weekly_low,
            weekly_distance_high_m=weekly_high,
            current_weekly_distance_m=round(base_weekly, 1),
            long_run_low_m=long_low,
            long_run_high_m=long_high,
            quality_sessions_low=quality_low,
            quality_sessions_high=quality_high,
        ),
        intensity=diagnostics.intensity,
        load=diagnostics.load,
        warnings=diagnostics.warnings,
        notes=notes,
    )


def _record(activity: Activity, offset: timedelta) -> RunRecord:
    return RunRecord(
        activity_id=activity.id,
        start_time_utc=activity.start_time_utc,
        local_date=(as_utc(activity.start_time_utc) + offset).date(),
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


def _hr_reference(records: list[RunRecord]) -> float | None:
    max_values = [record.max_hr for record in records if record.max_hr]
    if max_values:
        return float(max(max_values))
    avg_values = [record.avg_hr for record in records if record.avg_hr]
    if avg_values:
        return float(max(avg_values)) * 1.08
    return None


def _select_goal(goals: list[RaceGoal], today: date) -> RaceGoal | None:
    future = [goal for goal in goals if goal.target_date and goal.target_date >= today]
    if future:
        return min(future, key=lambda goal: (goal.target_date, goal.distance_m))
    undated = sorted(
        (goal for goal in goals if goal.target_date is None),
        key=lambda goal: goal.distance_m,
    )
    return undated[0] if undated else None


def _has_goal_effort(db: Session, goal: RaceGoal | None, reference: datetime) -> bool:
    if goal is None:
        return False
    count = db.scalar(
        select(func.count(BestEffort.id))
        .join(Activity)
        .where(
            BestEffort.distance_m == goal.distance_m,
            Activity.sport == "running",
            Activity.start_time_utc >= reference - timedelta(days=365),
        )
    )
    return bool(count)


def _readiness(db: Session, today: date) -> tuple[list[float], float | None]:
    rows = db.scalars(
        select(ExternalMetric)
        .where(
            ExternalMetric.metric == "training_readiness",
            ExternalMetric.metric_date >= today - timedelta(days=27),
            ExternalMetric.metric_date <= today,
        )
        .order_by(ExternalMetric.metric_date)
    ).all()
    values = [row.value for row in rows]
    if not values:
        return [], None
    return values, round(sum(values) / len(values), 1)


def _coverage_confidence(records: list[RunRecord], week_starts: set[date]) -> float:
    if not records:
        return 0.08
    score = min(len(records) / 18.0, 1.0) * 0.55
    score += min(len(week_starts) / 10.0, 1.0) * 0.35
    score += 0.10
    if any(record.has_streams for record in records):
        score += 0.05
    return round(clamp(score, 0.10, 0.95), 2)


def _dimension(
    key: str,
    score: float | None,
    reasons: list[str],
    metrics: dict[str, float | None],
    confidence: float,
) -> DimensionOut:
    confidence = round(clamp(confidence, 0.05, 0.98), 2)
    return DimensionOut(
        key=key,
        score=score,
        status=status_for(score),
        confidence=confidence_label(confidence),
        confidence_score=confidence,
        reasons=reasons,
        metrics={
            name: _round_metric(name, value) for name, value in metrics.items() if value is not None
        },
    )


def _round_metric(name: str, value: float | None) -> float:
    if value is None:
        return 0.0
    if name.endswith("_share") or name == "trail_share":
        return round(value, 4)
    if name in {"ratio", "runs_per_week", "rest_days_per_week"}:
        return round(value, 2)
    return round(value, 1)


def _limiters(dimensions: list[DimensionOut]) -> list[LimiterOut]:
    candidates = [
        dimension
        for dimension in dimensions
        if dimension.score is not None and dimension.score < 70
    ]
    candidates.sort(
        key=lambda dimension: (
            dimension.score or 0.0,
            -DIMENSION_WEIGHTS[dimension.key],
        )
    )
    return [
        LimiterOut(
            dimension_key=dimension.key,
            priority=index,
            score=dimension.score or 0.0,
            impact=round((70.0 - (dimension.score or 0.0)) * DIMENSION_WEIGHTS[dimension.key], 1),
            reasons=dimension.reasons,
            metrics=dimension.metrics,
        )
        for index, dimension in enumerate(candidates[:3], start=1)
    ]


def _focus(diagnostics: DiagnosticsOverview) -> list[TrainingFocusOut]:
    if diagnostics.status == "insufficient":
        return []
    if not diagnostics.limiters:
        return [
            TrainingFocusOut(
                dimension_key="balanced",
                priority=1,
                score=diagnostics.score,
                action="maintain_balance",
                reasons=["balanced"],
                metrics={},
            )
        ]
    return [
        TrainingFocusOut(
            dimension_key=limiter.dimension_key,
            priority=limiter.priority,
            score=limiter.score,
            action=ACTION_BY_DIMENSION.get(limiter.dimension_key, "maintain_balance"),
            reasons=limiter.reasons,
            metrics=limiter.metrics,
        )
        for limiter in diagnostics.limiters
    ]


def _intensity_out(intensity) -> IntensityOut:
    return IntensityOut(
        buckets=[
            IntensityBucketOut(
                key=bucket.key,
                sessions=bucket.sessions,
                duration_s=round(bucket.duration_s, 1),
                distance_m=round(bucket.distance_m, 1),
                share=bucket.share,
            )
            for bucket in intensity.buckets
        ],
        targets=[
            IntensityTargetOut(key=key, low=low, high=high)
            for key, (low, high) in INTENSITY_TARGETS.items()
        ],
        classified_sessions=intensity.classified_sessions,
        unknown_sessions=intensity.unknown_sessions,
        score=intensity.score,
        status=intensity.status,
        reasons=intensity.reasons,
    )


def _load_out(load: LoadSummary) -> LoadOut:
    return LoadOut(
        weekly=[
            WeeklyLoadOut(
                week_start=point.week_start,
                distance_m=point.distance_m,
                duration_s=point.duration_s,
                load=point.load,
                sessions=point.sessions,
            )
            for point in load.weekly
        ],
        acute_7d=load.acute_7d,
        chronic_weekly=load.chronic_weekly,
        ratio=load.ratio,
        ramp_pct=load.ramp_pct,
        score=load.score,
        status=load.status,
        reasons=load.reasons,
    )


def _quality_target(phase: Phase, avoid_quality: bool) -> tuple[int, int]:
    if avoid_quality or phase.key == "recovery":
        return 0, 0
    if phase.key == "taper":
        return 1, 1
    if phase.key == "build":
        return 1, 2
    if phase.key == "peak":
        return 2, 2
    return 1, 1


def _metric(
    diagnostics: DiagnosticsOverview,
    dimension_key: str,
    metric: str,
) -> float | None:
    for dimension in diagnostics.dimensions:
        if dimension.key == dimension_key:
            return dimension.metrics.get(metric)
    return None


def _dimension_status(diagnostics: DiagnosticsOverview, dimension_key: str) -> str:
    for dimension in diagnostics.dimensions:
        if dimension.key == dimension_key:
            return dimension.status
    return "unknown"


def _goal_out(goal: RaceGoal) -> GoalOut:
    return GoalOut(
        distance_m=goal.distance_m,
        target_time_s=goal.target_time_s,
        target_date=goal.target_date,
        race_name=goal.race_name,
        notes=goal.notes,
        updated_at=goal.updated_at,
    )
