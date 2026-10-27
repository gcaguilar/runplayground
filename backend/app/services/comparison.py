"""Workout comparison (M7).

Two activities are compared as summaries, not as a controlled experiment. The
service checks whether the sessions are comparable at all (sport, distance,
duration, terrain), reports the shared metrics with their difference, and only
computes one-kilometre splits when both activities have distance and elapsed
streams. Missing data lowers the comparability score instead of producing a
confident story.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, StreamSample
from app.schemas import (
    ComparisonInsightOut,
    ComparisonMetricOut,
    ComparisonSideOut,
    ComparisonSplitOut,
    ComparisonView,
)
from app.services.analysis import clamp
from app.utils import utcnow

MODEL_VERSION = "m7.0"
PACE_MIN = 150.0
PACE_MAX = 1200.0
MAX_SPLITS = 30


def _side(activity: Activity) -> ComparisonSideOut:
    return ComparisonSideOut(
        activity_id=activity.id,
        name=activity.name,
        sport=activity.sport,
        sub_sport=activity.sub_sport,
        start_time_utc=activity.start_time_utc,
        distance_m=round(activity.distance_m, 1),
        duration_s=round(activity.duration_s, 1),
        pace_s_per_km=round(activity.avg_pace_s_per_km, 1) if activity.avg_pace_s_per_km else None,
        avg_hr=activity.avg_hr,
        max_hr=activity.max_hr,
        cadence_spm=round(activity.avg_cadence_spm, 1) if activity.avg_cadence_spm else None,
        power_w=round(activity.avg_power_w, 1) if activity.avg_power_w else None,
        elevation_gain_m=round(activity.elevation_gain_m, 1)
        if activity.elevation_gain_m is not None
        else None,
        is_race=activity.is_race,
        has_streams=activity.has_streams,
        has_gps=activity.has_gps,
        training_effect=activity.training_effect,
        training_load=activity.training_load,
    )


def _ratio(left: float, right: float) -> float:
    low = min(left, right)
    high = max(left, right)
    return high / low if low > 0 else 1.0


def _elevation_per_km(activity: Activity) -> float | None:
    if activity.elevation_gain_m is None or activity.distance_m <= 0:
        return None
    return float(activity.elevation_gain_m) / (activity.distance_m / 1000.0)


def _comparability(
    left: Activity,
    right: Activity,
) -> tuple[str, float, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    score = 1.0
    hard = False

    if left.sport != right.sport:
        hard = True
        score = 0.0
        reasons.append("different_sport")
    else:
        left_trail = left.sub_sport == "trail_running"
        right_trail = right.sub_sport == "trail_running"
        if left_trail != right_trail:
            score -= 0.20
            reasons.append("different_terrain")

    if left.distance_m > 0 and right.distance_m > 0:
        distance_ratio = _ratio(left.distance_m, right.distance_m)
        if distance_ratio >= 1.60:
            hard = True
            score -= 0.35
            reasons.append("distance_mismatch")
        elif distance_ratio >= 1.25:
            score -= 0.15
            reasons.append("distance_gap")
    if left.duration_s > 0 and right.duration_s > 0:
        duration_ratio = _ratio(left.duration_s, right.duration_s)
        if duration_ratio >= 1.50:
            score -= 0.10
            reasons.append("duration_gap")

    left_elevation = _elevation_per_km(left)
    right_elevation = _elevation_per_km(right)
    if left_elevation is not None and right_elevation is not None:
        difference = abs(left_elevation - right_elevation)
        if difference >= 15.0:
            score -= 0.20
            reasons.append("terrain_gap")
        elif difference >= 8.0:
            score -= 0.10
            reasons.append("terrain_small_gap")

    if not (left.has_streams and right.has_streams):
        score -= 0.10
        warnings.append("missing_streams")
    if left.avg_hr is None or right.avg_hr is None:
        score -= 0.15
        warnings.append("missing_hr")
    if left.avg_cadence_spm is None or right.avg_cadence_spm is None:
        warnings.append("missing_cadence")
    if left.is_race != right.is_race:
        score -= 0.05
        warnings.append("race_vs_training")

    score = round(clamp(score, 0.0, 1.0), 2)
    if hard or score < 0.55:
        status = "not_comparable"
    elif score < 0.80:
        status = "limited"
    else:
        status = "comparable"
    return status, score, reasons, warnings


def _metric(
    key: str,
    left: float | None,
    right: float | None,
    direction: str,
    threshold_pct: float,
) -> ComparisonMetricOut:
    if left is None or right is None:
        return ComparisonMetricOut(
            key=key,
            left=left,
            right=right,
            direction=direction,
            better="unknown",
        )
    delta = right - left
    delta_pct = delta / left * 100.0 if left else None
    better = "unknown"
    if direction in {"lower", "higher"} and delta_pct is not None:
        if abs(delta_pct) <= threshold_pct:
            better = "similar"
        elif direction == "lower":
            better = "left" if left < right else "right"
        else:
            better = "left" if left > right else "right"
    return ComparisonMetricOut(
        key=key,
        left=round(left, 1),
        right=round(right, 1),
        delta=round(delta, 1),
        delta_pct=round(delta_pct, 1) if delta_pct is not None else None,
        direction=direction,
        better=better,
    )


def _metrics(left: ComparisonSideOut, right: ComparisonSideOut) -> list[ComparisonMetricOut]:
    return [
        _metric("pace_s_per_km", left.pace_s_per_km, right.pace_s_per_km, "lower", 1.0),
        _metric("avg_hr", left.avg_hr, right.avg_hr, "lower", 2.0),
        _metric("max_hr", left.max_hr, right.max_hr, "context", 2.0),
        _metric("cadence_spm", left.cadence_spm, right.cadence_spm, "context", 2.0),
        _metric("power_w", left.power_w, right.power_w, "context", 2.0),
        _metric("elevation_gain_m", left.elevation_gain_m, right.elevation_gain_m, "context", 5.0),
        _metric("training_effect", left.training_effect, right.training_effect, "context", 5.0),
        _metric("training_load", left.training_load, right.training_load, "context", 5.0),
    ]


def _stream_rows(db: Session, activity_id: int) -> list[tuple[float, float, int | None]]:
    rows = db.execute(
        select(StreamSample.distance_m, StreamSample.elapsed_s, StreamSample.heart_rate)
        .where(
            StreamSample.activity_id == activity_id,
            StreamSample.distance_m.is_not(None),
            StreamSample.elapsed_s.is_not(None),
        )
        .order_by(StreamSample.sample_index)
    ).all()
    return [
        (float(distance), float(elapsed), heart_rate)
        for distance, elapsed, heart_rate in rows
        if distance is not None and elapsed is not None
    ]


def _time_at(
    points: list[tuple[float, float, int | None]],
    distance_m: float,
) -> tuple[float, int | None] | None:
    previous: tuple[float, float, int | None] | None = None
    for point in points:
        distance, elapsed, heart_rate = point
        if distance >= distance_m:
            if previous is None or distance <= previous[0]:
                return elapsed, heart_rate
            span = distance - previous[0]
            fraction = (distance_m - previous[0]) / span if span > 0 else 1.0
            return previous[1] + fraction * (elapsed - previous[1]), heart_rate
        previous = point
    return None


def _km_splits(db: Session, activity: Activity) -> dict[int, tuple[float, int | None]]:
    points = _stream_rows(db, activity.id)
    if len(points) < 2:
        return {}
    max_km = min(int(points[-1][0] // 1000), MAX_SPLITS)
    output: dict[int, tuple[float, int | None]] = {}
    previous_time = 0.0
    for km in range(1, max_km + 1):
        boundary = float(km * 1000)
        current = _time_at(points, boundary)
        if current is None:
            break
        elapsed, boundary_hr = current
        pace = elapsed - previous_time
        if PACE_MIN <= pace <= PACE_MAX:
            heart_rates = [
                heart_rate
                for distance, _elapsed, heart_rate in points
                if (boundary - 1000) < distance <= boundary and heart_rate is not None
            ]
            heart_rate = round(sum(heart_rates) / len(heart_rates)) if heart_rates else boundary_hr
            output[km] = (round(pace, 1), heart_rate)
        previous_time = elapsed
    return output


def _splits(db: Session, left: Activity, right: Activity) -> list[ComparisonSplitOut]:
    left_splits = _km_splits(db, left)
    right_splits = _km_splits(db, right)
    common = sorted(set(left_splits) & set(right_splits))[:MAX_SPLITS]
    output: list[ComparisonSplitOut] = []
    for km in common:
        left_pace, left_hr = left_splits[km]
        right_pace, right_hr = right_splits[km]
        output.append(
            ComparisonSplitOut(
                index=km,
                distance_m=float(km * 1000),
                left_pace_s_per_km=left_pace,
                right_pace_s_per_km=right_pace,
                left_hr=left_hr,
                right_hr=right_hr,
                pace_delta_s=round(right_pace - left_pace, 1),
            )
        )
    return output


def _insights(
    left: ComparisonSideOut,
    right: ComparisonSideOut,
    metrics: list[ComparisonMetricOut],
    status: str,
) -> list[ComparisonInsightOut]:
    output: list[ComparisonInsightOut] = []
    if status == "not_comparable":
        return [ComparisonInsightOut(key="comparison_not_comparable")]
    by_key = {metric.key: metric for metric in metrics}
    pace = by_key.get("pace_s_per_km")
    if (
        pace
        and pace.left is not None
        and pace.right is not None
        and left.avg_hr is not None
        and right.avg_hr is not None
    ):
        pace_delta = right.pace_s_per_km - left.pace_s_per_km  # type: ignore[operator]
        hr_delta = (right.avg_hr or 0) - (left.avg_hr or 0)
        pace_pct = pace_delta / max(1.0, left.pace_s_per_km or 1.0) * 100.0
        if abs(pace_pct) <= 1.0 and abs(hr_delta) <= 2:
            output.append(ComparisonInsightOut(key="similar_effort"))
        elif pace_delta < -3.0:
            if hr_delta <= 2:
                output.append(
                    ComparisonInsightOut(
                        key="faster_same_effort",
                        value=round(abs(pace_delta), 1),
                    )
                )
            else:
                output.append(
                    ComparisonInsightOut(
                        key="faster_higher_effort",
                        value=round(abs(pace_delta), 1),
                        params={"hr_delta": abs(hr_delta)},
                    )
                )
        elif pace_delta > 3.0:
            if abs(hr_delta) <= 2:
                output.append(
                    ComparisonInsightOut(
                        key="slower_same_effort",
                        value=round(pace_delta, 1),
                    )
                )
            elif hr_delta >= 2:
                output.append(
                    ComparisonInsightOut(
                        key="slower_higher_effort",
                        value=round(pace_delta, 1),
                        params={"hr_delta": hr_delta},
                    )
                )
            else:
                output.append(
                    ComparisonInsightOut(
                        key="slower_lower_effort",
                        value=round(pace_delta, 1),
                        params={"hr_delta": abs(hr_delta)},
                    )
                )
        elif abs(pace_pct) <= 1.0 and hr_delta <= -3:
            output.append(
                ComparisonInsightOut(
                    key="similar_pace_lower_hr",
                    value=abs(hr_delta),
                )
            )

    if left.distance_m > 0 and right.distance_m > 0:
        ratio = _ratio(left.distance_m, right.distance_m)
        if ratio >= 1.15:
            output.append(
                ComparisonInsightOut(
                    key="longer_session",
                    value=round(abs(right.distance_m - left.distance_m), 1),
                )
            )
    left_elevation = (
        left.elevation_gain_m / (left.distance_m / 1000.0)
        if left.elevation_gain_m is not None and left.distance_m > 0
        else None
    )
    right_elevation = (
        right.elevation_gain_m / (right.distance_m / 1000.0)
        if right.elevation_gain_m is not None and right.distance_m > 0
        else None
    )
    if (
        left_elevation is not None
        and right_elevation is not None
        and abs(left_elevation - right_elevation) >= 5.0
    ):
        output.append(
            ComparisonInsightOut(
                key="terrain_difference",
                value=round(abs(left_elevation - right_elevation), 1),
            )
        )
    if not output:
        output.append(ComparisonInsightOut(key="no_clear_difference"))
    return output[:4]


def build_comparison(
    db: Session,
    left_id: int,
    right_id: int,
    now: datetime | None = None,
) -> ComparisonView | None:
    left = db.get(Activity, left_id)
    right = db.get(Activity, right_id)
    if left is None or right is None:
        return None
    reference = now or utcnow()
    status, score, reasons, warnings = _comparability(left, right)
    left_side = _side(left)
    right_side = _side(right)
    metrics = _metrics(left_side, right_side)
    splits = _splits(db, left, right)
    if not splits and "missing_streams" not in warnings:
        warnings.append("no_splits")
    insights = _insights(left_side, right_side, metrics, status)

    notes = [
        "summary_metrics_only",
        "conditions_not_controlled",
        "association_not_causation",
        "not_medical_advice",
    ]
    if not splits:
        notes.append("no_split_streams")
    return ComparisonView(
        generated_at=reference,
        model_version=MODEL_VERSION,
        status=status,
        comparability=score,
        left=left_side,
        right=right_side,
        metrics=metrics,
        splits=splits,
        insights=insights,
        reasons=reasons,
        warnings=warnings,
        notes=notes,
    )
