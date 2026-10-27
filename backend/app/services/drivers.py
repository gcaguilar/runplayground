"""Which training factors coincide with fitness improvements (M4).

This is an association analysis, not a causal model. Weekly training totals are
paired with the fitness change observed in the same week's prediction snapshot;
for each factor we report Pearson's correlation, the median split (above/below
median) and how many paired weeks support it. With few weeks the result is
explicitly marked as insufficient.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, PerformanceSnapshot
from app.schemas import DriverAnalysisOut, DriverOut
from app.services.analysis import (
    RunRecord,
    classify_run,
    session_load,
    week_start,
)
from app.utils import as_utc

MIN_PAIRED_WEEKS = 4
SNAPSHOT_GAP_DAYS = 21


@dataclass
class WeekFeature:
    week_start: date
    fitness_s: float | None
    volume_m: float = 0.0
    sessions: int = 0
    longest_m: float = 0.0
    quality_sessions: int = 0
    active_days: int = 0
    load: float = 0.0


FACTOR_KEYS: tuple[str, ...] = (
    "volume_m",
    "sessions",
    "longest_m",
    "quality_sessions",
    "active_days",
    "load",
)


def _run_records(db: Session, start: date, end: date, offset: timedelta) -> list[RunRecord]:
    margin = timedelta(days=2)
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc
            >= datetime(start.year, start.month, start.day) - offset - margin,
            Activity.start_time_utc
            <= datetime(end.year, end.month, end.day) - offset + timedelta(days=1) + margin,
        )
        .order_by(Activity.start_time_utc)
    ).all()
    output: list[RunRecord] = []
    for activity in rows:
        local = (as_utc(activity.start_time_utc) + offset).date()
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


def _snapshot_fitness(snapshot: PerformanceSnapshot) -> float | None:
    for item in snapshot.predictions or []:
        if not isinstance(item, dict):
            continue
        if item.get("distance_key") == "10k" and item.get("planning_s") is not None:
            return float(item["planning_s"])
    return snapshot.fitness_anchor_s


def _weekly_features(
    db: Session,
    start: date,
    end: date,
    offset: timedelta,
    threshold_pace: float | None,
    hr_reference: float | None,
    mode: str = "auto",
    threshold_hr: float | None = None,
) -> list[WeekFeature]:
    first = week_start(start)
    last = week_start(end)
    weeks: dict[date, WeekFeature] = {}
    current = first
    while current <= last:
        weeks[current] = WeekFeature(week_start=current, fitness_s=None)
        current += timedelta(days=7)

    snapshots = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= start,
            PerformanceSnapshot.snapshot_date <= end,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()
    for snapshot in snapshots:
        key = week_start(snapshot.snapshot_date)
        bucket = weeks.get(key)
        if bucket is None:
            continue
        fitness = _snapshot_fitness(snapshot)
        if fitness is not None:
            bucket.fitness_s = fitness

    records = _run_records(db, start, end, offset)
    days: dict[date, set[date]] = {key: set() for key in weeks}
    for record in records:
        key = week_start(record.local_date)
        bucket = weeks.get(key)
        if bucket is None:
            continue
        bucket.volume_m += record.distance_m
        bucket.sessions += 1
        bucket.longest_m = max(bucket.longest_m, record.distance_m)
        bucket.load += session_load(record, threshold_pace)
        days[key].add(record.local_date)
        if classify_run(
            record,
            threshold_pace,
            hr_reference,
            mode=mode,
            threshold_hr=threshold_hr,
        ) == "hard" and (record.duration_s >= 600 or record.distance_m >= 3000):
            bucket.quality_sessions += 1
    for key, bucket in weeks.items():
        bucket.active_days = len(days[key])
        bucket.volume_m = round(bucket.volume_m, 1)
        bucket.longest_m = round(bucket.longest_m, 1)
        bucket.load = round(bucket.load, 1)
    return sorted(weeks.values(), key=lambda item: item.week_start)


def _paired_weeks(weeks: list[WeekFeature]) -> list[tuple[WeekFeature, float]]:
    """Pair a week's training with the fitness change since the previous snapshot."""

    with_fitness = [week for week in weeks if week.fitness_s is not None]
    pairs: list[tuple[WeekFeature, float]] = []
    for previous, current in zip(with_fitness, with_fitness[1:], strict=False):
        if previous.fitness_s is None or current.fitness_s is None:
            continue
        gap = (current.week_start - previous.week_start).days
        if gap > SNAPSHOT_GAP_DAYS:
            continue
        improvement = (
            (previous.fitness_s - current.fitness_s) / max(1.0, previous.fitness_s) * 100.0
        )
        pairs.append((current, round(improvement, 2)))
    return pairs


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x <= 0 or variance_y <= 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _driver(
    key: str,
    pairs: list[tuple[WeekFeature, float]],
) -> DriverOut:
    values = [float(getattr(week, key)) for week, _improvement in pairs]
    improvements = [improvement for _week, improvement in pairs]
    samples = len(pairs)
    correlation = _pearson(values, improvements) if samples >= MIN_PAIRED_WEEKS else None
    direction = "unknown"
    strength = "unknown"
    if correlation is not None:
        if correlation > 0.05:
            direction = "positive"
        elif correlation < -0.05:
            direction = "negative"
        else:
            direction = "none"
        absolute = abs(correlation)
        strength = "strong" if absolute >= 0.5 else "moderate" if absolute >= 0.3 else "weak"

    high_improvement = low_improvement = difference = None
    if samples >= MIN_PAIRED_WEEKS:
        cutoff = median(values)
        value_pairs = list(zip(values, improvements, strict=True))
        high = [improvement for value, improvement in value_pairs if value >= cutoff]
        low = [improvement for value, improvement in value_pairs if value < cutoff]
        if high:
            high_improvement = round(sum(high) / len(high), 2)
        if low:
            low_improvement = round(sum(low) / len(low), 2)
        if high_improvement is not None and low_improvement is not None:
            difference = round(high_improvement - low_improvement, 2)

    reasons: list[str] = ["association_not_causation"]
    if samples < MIN_PAIRED_WEEKS:
        reasons.append("few_samples")
    elif samples < 8:
        reasons.append("small_sample")
    if correlation is not None:
        absolute = abs(correlation)
        if absolute >= 0.5:
            reasons.append("strong_association")
        elif absolute >= 0.3:
            reasons.append("moderate_association")
        else:
            reasons.append("weak_association")

    if correlation is None or samples < 6:
        confidence = "low"
    elif samples >= 10 and abs(correlation) >= 0.45:
        confidence = "high"
    elif abs(correlation) >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    return DriverOut(
        key=key,
        correlation=round(correlation, 3) if correlation is not None else None,
        direction=direction,
        strength=strength,
        samples=samples,
        improvement_high_pct=high_improvement,
        improvement_low_pct=low_improvement,
        difference_pct=difference,
        confidence=confidence,
        reasons=reasons,
    )


def build_drivers(
    db: Session,
    start: date,
    end: date,
    offset: timedelta,
    *,
    threshold_pace: float | None,
    hr_reference: float | None,
    mode: str = "auto",
    threshold_hr: float | None = None,
) -> DriverAnalysisOut:
    weeks = _weekly_features(
        db,
        start,
        end,
        offset,
        threshold_pace,
        hr_reference,
        mode=mode,
        threshold_hr=threshold_hr,
    )
    pairs = _paired_weeks(weeks)
    drivers = [_driver(key, pairs) for key in FACTOR_KEYS]
    drivers.sort(
        key=lambda item: (
            abs(item.correlation) if item.correlation is not None else -1.0,
            item.samples,
        ),
        reverse=True,
    )

    warnings: list[str] = []
    fitness_weeks = [week for week in weeks if week.fitness_s is not None]
    if not fitness_weeks:
        warnings.append("no_snapshots")
    elif len(fitness_weeks) < 6:
        warnings.append("short_driver_history")
    if len(pairs) < 6:
        warnings.append("few_paired_weeks")
    if not any(week.sessions > 0 for week in weeks):
        warnings.append("no_recent_volume")
    if len(fitness_weeks) >= 2:
        gaps = [
            (right.week_start - left.week_start).days
            for left, right in zip(fitness_weeks, fitness_weeks[1:], strict=False)
        ]
        if gaps and max(gaps) > SNAPSHOT_GAP_DAYS:
            warnings.append("snapshot_gaps")

    status = "ok" if len(pairs) >= MIN_PAIRED_WEEKS else "insufficient"
    notes = [
        "association_not_causation",
        "weekly_pairs",
        "improvement_is_fitness_change",
        "features_are_measured",
        "classification_uses_current_anchor",
        "load_is_estimated",
    ]
    if mode != "auto":
        notes.append("manual_thresholds_applied")
    return DriverAnalysisOut(
        status=status,
        window_days=(end - start).days + 1,
        weeks=len(fitness_weeks),
        samples=len(pairs),
        drivers=drivers,
        warnings=warnings,
        notes=notes,
    )
