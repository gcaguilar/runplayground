"""Continuous tracking for M4.

Two things are tracked here:

* **Prediction accuracy** — daily prediction snapshots are matched with the
  first real result observed after each snapshot. The result can be a race or a
  best effort from training; the sample says which one, so a training split is
  never presented as an official race.
* **Goal and action tracking** — goal revisions store what was asked for and
  what the model predicted at the time, while tracked actions store a baseline
  score so a later review can say whether the related dimension improved,
  stayed stable or got worse.

Accuracy is observational. A small sample, a training effort instead of a race,
or a prediction made long before the result all widen the interpretation. The
API returns those caveats instead of a single flattering percentage.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    BestEffort,
    GoalRevision,
    PerformanceSnapshot,
    RaceGoal,
    TrackedAction,
)
from app.schemas import (
    AccuracySampleOut,
    AccuracySummaryOut,
    ActionSuggestionOut,
    ActionUpsert,
    GoalHistoryPointOut,
    GoalResultOut,
    GoalRevisionOut,
    GoalTrackingOut,
    PredictionAccuracyOut,
    TrackedActionOut,
    TrackingOverview,
)
from app.services.analysis import DIMENSION_WEIGHTS, clamp
from app.services.analysis_settings import get_analysis_settings
from app.services.diagnostics import ACTION_BY_DIMENSION, build_diagnostics
from app.services.drivers import build_drivers
from app.services.performance import build_overview, ensure_efforts, store_snapshot
from app.services.performance_models import STANDARD_DISTANCES, round_prediction_time
from app.utils import as_utc, utcnow

MODEL_VERSION = "m4.0"
DEFAULT_DAYS = 180
MAX_MATCH_DAYS = 90
HORIZONS = (("0_28", 0, 28), ("29_56", 29, 56), ("57_90", 57, 90))
VALID_DIMENSIONS = set(DIMENSION_WEIGHTS)


def _distance_key(distance_m: float) -> str:
    for key, standard in STANDARD_DISTANCES:
        if abs(standard - distance_m) / standard <= 0.025:
            return key
    return f"{distance_m / 1000.0:.1f}k"


def _summary(
    scope: str,
    key: str,
    samples: list[AccuracySampleOut],
) -> AccuracySummaryOut | None:
    if not samples:
        return None
    count = len(samples)
    bias = sum(sample.error_s for sample in samples) / count
    bias_pct = sum(sample.error_pct for sample in samples) / count
    mae = sum(abs(sample.error_s) for sample in samples) / count
    mape = sum(abs(sample.error_pct) for sample in samples) / count
    inside = sum(1 for sample in samples if sample.within_range) / count * 100.0
    return AccuracySummaryOut(
        scope=scope,
        key=key,
        samples=count,
        mean_bias_s=round(bias, 1),
        mean_bias_pct=round(bias_pct, 1),
        mae_s=round(mae, 1),
        mape_pct=round(mape, 1),
        within_range_pct=round(inside, 1),
    )


def _snapshot_predictions(snapshot: PerformanceSnapshot) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in snapshot.predictions or []:
        if not isinstance(item, dict):
            continue
        key = item.get("distance_key")
        if key and item.get("planning_s") is not None:
            output[key] = item
    return output


def _hr_reference(db: Session, start: date, end: date, offset: timedelta) -> float | None:
    rows = db.scalars(
        select(Activity).where(
            Activity.sport == "running",
            Activity.start_time_utc
            >= datetime(start.year, start.month, start.day) - offset - timedelta(days=2),
            Activity.start_time_utc
            <= datetime(end.year, end.month, end.day) - offset + timedelta(days=3),
        )
    ).all()
    maximums = [float(activity.max_hr) for activity in rows if activity.max_hr]
    if maximums:
        return max(maximums)
    averages = [float(activity.avg_hr) for activity in rows if activity.avg_hr]
    return max(averages) * 1.08 if averages else None


def _accuracy(db: Session, start: date, end: date, offset: timedelta) -> PredictionAccuracyOut:
    snapshots = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= start - timedelta(days=MAX_MATCH_DAYS),
            PerformanceSnapshot.snapshot_date <= end,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    by_distance: dict[str, list[PerformanceSnapshot]] = {}
    for snapshot in snapshots:
        hidden = _snapshot_predictions(snapshot)
        for key, prediction in hidden.items():
            if prediction.get("planning_s") is not None:
                by_distance.setdefault(key, []).append(snapshot)

    distance_values = {key: distance for key, distance in STANDARD_DISTANCES}
    actuals = db.execute(
        select(BestEffort, Activity)
        .join(Activity, BestEffort.activity_id == Activity.id)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc >= datetime(start.year, start.month, start.day) - offset,
            Activity.start_time_utc
            <= datetime(end.year, end.month, end.day) - offset + timedelta(days=1),
            BestEffort.distance_m.in_(list(distance_values.values())),
        )
        .order_by(Activity.start_time_utc, BestEffort.distance_m)
    ).all()

    samples: list[AccuracySampleOut] = []
    for effort, activity in actuals:
        if activity.sub_sport == "trail_running" or activity.duration_s <= 0:
            continue
        actual_date = (as_utc(activity.start_time_utc) + offset).date()
        key = _distance_key(effort.distance_m)
        candidates = [
            snapshot
            for snapshot in by_distance.get(key, [])
            if snapshot.snapshot_date < actual_date
            and (actual_date - snapshot.snapshot_date).days <= MAX_MATCH_DAYS
        ]
        if not candidates:
            continue
        snapshot = max(candidates, key=lambda item: item.snapshot_date)
        prediction = _snapshot_predictions(snapshot).get(key)
        if prediction is None or prediction.get("planning_s") is None:
            continue
        predicted = float(prediction["planning_s"])
        low = prediction.get("planning_low_s")
        high = prediction.get("planning_high_s")
        error = activity.duration_s - predicted
        samples.append(
            AccuracySampleOut(
                distance_key=key,
                distance_m=effort.distance_m,
                predicted_on=snapshot.snapshot_date,
                actual_on=actual_date,
                horizon_days=(actual_date - snapshot.snapshot_date).days,
                predicted_s=round(predicted, 1),
                predicted_low_s=round(float(low), 1) if low is not None else None,
                predicted_high_s=round(float(high), 1) if high is not None else None,
                actual_s=round(activity.duration_s, 1),
                activity_id=activity.id,
                activity_name=activity.name,
                is_race=activity.is_race,
                error_s=round(error, 1),
                error_pct=round(error / max(1.0, predicted) * 100.0, 1),
                within_range=(
                    low is not None
                    and high is not None
                    and float(low) <= activity.duration_s <= float(high)
                ),
            )
        )

    samples.sort(key=lambda item: (item.actual_on, item.distance_m), reverse=True)
    samples = samples[:400]

    by_distance_out: list[AccuracySummaryOut] = []
    for key, _distance in STANDARD_DISTANCES:
        summary = _summary(
            "distance",
            key,
            [item for item in samples if item.distance_key == key],
        )
        if summary is not None:
            by_distance_out.append(summary)
    by_horizon_out: list[AccuracySummaryOut] = []
    for key, low, high in HORIZONS:
        summary = _summary(
            "horizon",
            key,
            [item for item in samples if low <= item.horizon_days <= high],
        )
        if summary is not None:
            by_horizon_out.append(summary)

    notes: list[str] = []
    if not samples:
        notes.append("no_accuracy_samples")
    else:
        notes.append("predictions_from_daily_snapshots")
        notes.append("training_efforts_counted")
        notes.append("accuracy_is_observational")
        if any(not item.is_race for item in samples):
            notes.append("non_race_results_included")
        if len(samples) < 5:
            notes.append("small_sample")

    return PredictionAccuracyOut(
        samples=samples,
        overall=_summary("overall", "all", samples),
        by_distance=by_distance_out,
        by_horizon=by_horizon_out,
        notes=notes,
    )


def _goal_history(
    snapshots: list[PerformanceSnapshot], key: str, target_time_s: float
) -> list[GoalHistoryPointOut]:
    points: list[GoalHistoryPointOut] = []
    for snapshot in snapshots:
        prediction = _snapshot_predictions(snapshot).get(key)
        if prediction is None or prediction.get("planning_s") is None:
            continue
        predicted = float(prediction["planning_s"])
        points.append(
            GoalHistoryPointOut(
                date=snapshot.snapshot_date,
                predicted_s=round(predicted, 1),
                gap_s=round(target_time_s - predicted, 1),
            )
        )
    return points


def _results_for_distance(
    db: Session,
    distance_m: float,
    start: date,
    end: date,
    offset: timedelta,
) -> list[GoalResultOut]:
    rows = db.execute(
        select(BestEffort, Activity)
        .join(Activity, BestEffort.activity_id == Activity.id)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc
            >= datetime(start.year, start.month, start.day) - offset - timedelta(days=2),
            Activity.start_time_utc
            <= datetime(end.year, end.month, end.day) - offset + timedelta(days=1),
            BestEffort.distance_m == distance_m,
            Activity.duration_s > 0,
        )
        .order_by(Activity.start_time_utc)
    ).all()
    output: list[GoalResultOut] = []
    for _effort, activity in rows:
        if activity.sub_sport == "trail_running":
            continue
        output.append(
            GoalResultOut(
                date=(as_utc(activity.start_time_utc) + offset).date(),
                time_s=round(activity.duration_s, 1),
                activity_id=activity.id,
                activity_name=activity.name,
                is_race=activity.is_race,
                source="race" if activity.is_race else "effort",
            )
        )
    return output[-100:]


def _goal_trend(
    history: list[GoalHistoryPointOut],
    current_time_s: float | None,
    today: date,
) -> tuple[str, float | None, float | None]:
    if current_time_s is None or not history:
        return "unknown", None, None
    cutoff = today - timedelta(days=28)
    older = [point for point in history if point.date <= cutoff and point.predicted_s is not None]
    if not older:
        older = [
            point
            for point in history
            if point.date <= today - timedelta(days=14) and point.predicted_s is not None
        ]
    if not older:
        return "unknown", None, None
    baseline = max(older, key=lambda point: point.date)
    if baseline.predicted_s is None:
        return "unknown", None, None
    change = current_time_s - baseline.predicted_s
    change_pct = change / max(1.0, baseline.predicted_s) * 100.0
    if change_pct <= -0.5:
        trend = "improving"
    elif change_pct >= 0.5:
        trend = "worsening"
    else:
        trend = "stable"
    return trend, round(change, 1), round(change_pct, 1)


def _goal_out(
    goal: RaceGoal,
    current: tuple[float | None, float | None, float | None, str | None],
    history: list[GoalHistoryPointOut],
    results: list[GoalResultOut],
    revisions: list[GoalRevision],
    today: date,
) -> GoalTrackingOut:
    predicted, low, high, confidence = current
    gap = round(goal.target_time_s - predicted, 1) if predicted is not None else None
    gap_pct = (
        round(gap / max(1.0, predicted) * 100.0, 1)
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
    trend, change_s, change_pct = _goal_trend(history, predicted, today)
    days_to_target = (goal.target_date - today).days if goal.target_date else None

    revision_out: list[GoalRevisionOut] = []
    previous_target: float | None = None
    for revision in revisions:
        revision_out.append(
            GoalRevisionOut(
                created_at=revision.created_at,
                target_time_s=round(revision.target_time_s, 1),
                target_date=revision.target_date,
                race_name=revision.race_name,
                prediction_time_s=revision.prediction_time_s,
                prediction_low_s=revision.prediction_low_s,
                prediction_high_s=revision.prediction_high_s,
                confidence=revision.confidence,
                change_s=(
                    round(revision.target_time_s - previous_target, 1)
                    if previous_target is not None
                    else None
                ),
            )
        )
        previous_target = revision.target_time_s

    return GoalTrackingOut(
        distance_key=_distance_key(goal.distance_m),
        distance_m=goal.distance_m,
        target_time_s=round(goal.target_time_s, 1),
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
        trend=trend,
        change_28d_s=change_s,
        change_28d_pct=change_pct,
        days_to_target=days_to_target,
        last_reviewed_at=goal.updated_at,
        history=history,
        results=results,
        revisions=revision_out,
    )


def _prediction_for_distance(
    overview, distance_m: float
) -> tuple[float | None, float | None, float | None, str | None]:
    for item in overview.distances:
        if (
            abs(item.distance_m - distance_m) / max(1.0, item.distance_m) <= 0.025
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
    from app.services.performance_models import riegel_time

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


def _action_verdict(delta: float | None) -> str:
    if delta is None:
        return "unknown"
    if delta >= 5.0:
        return "improved"
    if delta <= -5.0:
        return "worse"
    return "stable"


def _tracked_action_out(
    action: TrackedAction,
    current_score: float | None,
    reasons: list[str],
) -> TrackedActionOut:
    delta = (
        round(current_score - action.baseline_score, 1)
        if current_score is not None and action.baseline_score is not None
        else None
    )
    return TrackedActionOut(
        dimension_key=action.dimension_key,
        status=action.status,
        note=action.note,
        created_at=action.created_at,
        updated_at=action.updated_at,
        completed_at=action.completed_at,
        baseline_score=action.baseline_score,
        baseline_confidence=action.baseline_confidence,
        current_score=current_score,
        delta=delta,
        verdict=_action_verdict(delta),
        reasons=reasons,
    )


def upsert_action(
    db: Session,
    dimension_key: str,
    payload: ActionUpsert,
    now: datetime | None = None,
) -> TrackedAction | None:
    if dimension_key not in VALID_DIMENSIONS:
        return None
    reference = now or utcnow()
    action = db.scalar(select(TrackedAction).where(TrackedAction.dimension_key == dimension_key))
    if action is None:
        diagnostics = build_diagnostics(db, reference)
        dimension = next(
            (item for item in diagnostics.dimensions if item.key == dimension_key),
            None,
        )
        action = TrackedAction(
            dimension_key=dimension_key,
            status=payload.status,
            note=payload.note.strip() if payload.note else None,
            baseline_score=dimension.score if dimension else None,
            baseline_confidence=dimension.confidence if dimension else None,
            baseline_metrics=dimension.metrics if dimension else {},
        )
        db.add(action)
    else:
        action.status = payload.status
        action.note = payload.note.strip() if payload.note else None
    action.completed_at = reference if payload.status == "completed" else None
    db.commit()
    db.refresh(action)
    return action


def delete_action(db: Session, dimension_key: str) -> bool:
    action = db.scalar(select(TrackedAction).where(TrackedAction.dimension_key == dimension_key))
    if action is None:
        return False
    db.delete(action)
    db.commit()
    return True


def build_tracking(
    db: Session,
    days: int = DEFAULT_DAYS,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> TrackingOverview:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()
    days = max(30, min(days, 730))
    start = today - timedelta(days=days - 1)

    ensure_efforts(db)
    diagnostics = build_diagnostics(db, reference, tz_offset_minutes)
    overview = build_overview(db, reference)
    analysis = get_analysis_settings(db, reference, overview=overview)
    store_snapshot(db, overview)
    accuracy = _accuracy(db, start, today, offset)
    drivers = build_drivers(
        db,
        start,
        today,
        offset,
        threshold_pace=analysis.threshold_pace_s_per_km,
        hr_reference=analysis.max_hr or _hr_reference(db, start, today, offset),
        mode=analysis.mode,
        threshold_hr=analysis.threshold_hr,
    )

    snapshots = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= start,
            PerformanceSnapshot.snapshot_date <= today,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    goals = db.scalars(select(RaceGoal).order_by(RaceGoal.distance_m)).all()
    goal_out: list[GoalTrackingOut] = []
    for goal in goals:
        key = _distance_key(goal.distance_m)
        revisions = db.scalars(
            select(GoalRevision)
            .where(GoalRevision.distance_m == goal.distance_m)
            .order_by(GoalRevision.created_at, GoalRevision.id)
        ).all()
        goal_out.append(
            _goal_out(
                goal,
                _prediction_for_distance(overview, goal.distance_m),
                _goal_history(snapshots, key, goal.target_time_s),
                _results_for_distance(db, goal.distance_m, start, today, offset),
                revisions,
                today,
            )
        )

    dimensions = {item.key: item for item in diagnostics.dimensions}
    tracked = db.scalars(select(TrackedAction).order_by(TrackedAction.created_at)).all()
    tracked_out = [
        _tracked_action_out(
            action,
            dimensions[action.dimension_key].score if action.dimension_key in dimensions else None,
            dimensions[action.dimension_key].reasons if action.dimension_key in dimensions else [],
        )
        for action in tracked
    ]
    tracked_keys = {action.dimension_key for action in tracked}
    suggestions = [
        ActionSuggestionOut(
            dimension_key=limiter.dimension_key,
            score=limiter.score,
            priority=limiter.priority,
            action=ACTION_BY_DIMENSION.get(limiter.dimension_key, "maintain_balance"),
            reasons=limiter.reasons,
            tracked=limiter.dimension_key in tracked_keys,
        )
        for limiter in diagnostics.limiters
    ]

    warnings: list[str] = []
    if not goals:
        warnings.append("no_goals")
    if not snapshots:
        warnings.append("no_snapshots")
    if accuracy.overall is None:
        warnings.append("no_accuracy_samples")
    elif accuracy.overall.samples < 5:
        warnings.append("small_accuracy_sample")
    if len(snapshots) < 2:
        warnings.append("short_history")
    for warning in drivers.warnings:
        if warning not in warnings:
            warnings.append(warning)

    notes = [
        "snapshots_are_daily",
        "accuracy_is_observational",
        "actions_do_not_claim_causality",
        "association_not_causation",
        "not_medical_advice",
    ]
    if analysis.has_manual:
        notes.append("manual_thresholds_applied")
    status = "ok" if accuracy.samples or goal_out else "insufficient"
    return TrackingOverview(
        generated_at=reference,
        model_version=MODEL_VERSION,
        days=days,
        status=status,
        accuracy=accuracy,
        drivers=drivers,
        goals=goal_out,
        actions=tracked_out,
        suggestions=suggestions,
        warnings=warnings,
        notes=notes,
    )
