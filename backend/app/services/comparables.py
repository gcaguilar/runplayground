"""Comparable pace–heart-rate analysis (M6).

The question is not "is my average pace better?" but "at the same heart rate
and in a comparable run, am I faster than before?". The service groups aerobic
runs by distance band and terrain, removes the within-group heart-rate effect
with a simple linear adjustment, and compares the earlier and later halves of
each group.

It is deliberately an association, not a physiological test. Groups need a
minimum of sessions and a minimum time span; if heart rate, elevation or the
number of comparable runs are missing, the response says so instead of
inventing a trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity
from app.schemas import (
    PaceHrAnalysisOut,
    PaceHrGroupOut,
    PaceHrLineOut,
    PaceHrPointOut,
)
from app.services.analysis import RunRecord, clamp, classify_run, confidence_label
from app.services.performance import build_overview, ensure_efforts
from app.utils import as_utc, utcnow

MODEL_VERSION = "m6.0"
MIN_DISTANCE_M = 4000.0
MIN_DURATION_S = 1200.0
MIN_GROUP_SESSIONS = 4
MIN_CONFIDENT_SESSIONS = 6
MIN_SPAN_DAYS = 28
STABLE_CHANGE_S = 1.5
PACE_MIN = 180.0
PACE_MAX = 900.0
DISTANCE_BANDS: tuple[tuple[float, float, str], ...] = (
    (4000.0, 8000.0, "short"),
    (8000.0, 12000.0, "medium"),
    (12000.0, 18000.0, "long"),
    (18000.0, 1_000_000.0, "very_long"),
)


@dataclass
class ComparableRun:
    activity_id: int
    name: str
    local_date: date
    pace_s_per_km: float
    avg_hr: int
    max_hr: int | None
    distance_m: float
    elevation_gain_m: float | None
    distance_band: str
    terrain_band: str
    group_key: str
    adjusted_pace_s_per_km: float | None = None
    period: str = ""


@dataclass
class GroupedRuns:
    key: str
    distance_band: str
    terrain_band: str
    runs: list[ComparableRun] = field(default_factory=list)
    reference_hr: float = 0.0
    early_pace: float | None = None
    recent_pace: float | None = None
    change_s: float | None = None
    change_pct: float | None = None
    status: str = "unknown"
    confidence_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    early_line: list[PaceHrLineOut] = field(default_factory=list)
    recent_line: list[PaceHrLineOut] = field(default_factory=list)


def _distance_band(distance_m: float) -> str:
    for low, high, key in DISTANCE_BANDS:
        if low <= distance_m < high:
            return key
    return "very_long"


def _terrain_band(activity: Activity) -> str:
    if activity.elevation_gain_m is None or activity.distance_m <= 0:
        return "unknown"
    per_km = float(activity.elevation_gain_m) / (activity.distance_m / 1000.0)
    if per_km < 5.0:
        return "flat"
    if per_km <= 12.0:
        return "rolling"
    return "hilly"


def _hr_reference(rows: list[Activity]) -> float | None:
    maximums = [float(row.max_hr) for row in rows if row.max_hr]
    if maximums:
        return max(maximums)
    averages = [float(row.avg_hr) for row in rows if row.avg_hr]
    return max(averages) * 1.08 if averages else None


def _fit(values: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    """Least-squares fit of pace on heart rate."""

    if len(values) < 2:
        return None, None
    mean_x = sum(x for x, _y in values) / len(values)
    mean_y = sum(y for _x, y in values) / len(values)
    variance = sum((x - mean_x) ** 2 for x, _y in values)
    if variance <= 0.5:
        return None, None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in values)
    slope = covariance / variance
    return slope, mean_y - slope * mean_x


def _line(values: list[tuple[float, float]]) -> list[PaceHrLineOut]:
    slope, intercept = _fit(values)
    if slope is None or intercept is None:
        return []
    xs = [x for x, _y in values]
    low, high = min(xs), max(xs)
    if high - low < 0.5:
        return []
    return [
        PaceHrLineOut(hr=round(low, 1), pace_s_per_km=round(intercept + slope * low, 1)),
        PaceHrLineOut(hr=round(high, 1), pace_s_per_km=round(intercept + slope * high, 1)),
    ]


def _group_confidence(group: GroupedRuns) -> tuple[float, list[str]]:
    if not group.runs:
        return 0.05, ["no_sessions"]
    sessions = len(group.runs)
    span = (group.runs[-1].local_date - group.runs[0].local_date).days
    hr_range = max(run.avg_hr for run in group.runs) - min(run.avg_hr for run in group.runs)
    score = 0.12
    score += min(sessions / 12.0, 1.0) * 0.30
    score += min(span / 56.0, 1.0) * 0.20
    score += min(hr_range / 25.0, 1.0) * 0.16
    if group.early_line and group.recent_line:
        score += 0.12
    if sessions >= 8 and span >= 42:
        score += 0.10
    reasons: list[str] = []
    if sessions < MIN_CONFIDENT_SESSIONS:
        reasons.append("few_sessions")
    if span < MIN_SPAN_DAYS:
        reasons.append("short_span")
    if hr_range < 10:
        reasons.append("narrow_hr_range")
    if not group.early_line or not group.recent_line:
        reasons.append("no_regression")
    reasons.append("temperature_not_controlled")
    return round(clamp(score, 0.05, 0.92), 2), reasons


def _build_group(key: str, runs: list[ComparableRun]) -> GroupedRuns:
    ordered = sorted(runs, key=lambda run: (run.local_date, run.activity_id))
    reference_hr = median(run.avg_hr for run in ordered)
    group = GroupedRuns(
        key=key,
        distance_band=ordered[0].distance_band,
        terrain_band=ordered[0].terrain_band,
        runs=ordered,
        reference_hr=round(reference_hr, 1),
    )
    values = [(float(run.avg_hr), run.pace_s_per_km) for run in ordered]
    slope, intercept = _fit(values)
    if slope is not None and intercept is not None:
        for run in ordered:
            run.adjusted_pace_s_per_km = round(
                run.pace_s_per_km - slope * (run.avg_hr - reference_hr),
                1,
            )
    else:
        for run in ordered:
            run.adjusted_pace_s_per_km = round(run.pace_s_per_km, 1)

    split = len(ordered) // 2
    early = ordered[:split]
    recent = ordered[split:]
    for run in early:
        run.period = "early"
    for run in recent:
        run.period = "recent"

    if len(early) >= 2 and len(recent) >= 2:
        group.early_pace = round(
            median(run.adjusted_pace_s_per_km or run.pace_s_per_km for run in early),
            1,
        )
        group.recent_pace = round(
            median(run.adjusted_pace_s_per_km or run.pace_s_per_km for run in recent),
            1,
        )
        group.change_s = round(group.recent_pace - group.early_pace, 1)
        group.change_pct = (
            round(group.change_s / group.early_pace * 100.0, 1) if group.early_pace > 0 else None
        )
        if group.change_s <= -STABLE_CHANGE_S:
            group.status = "improving"
        elif group.change_s >= STABLE_CHANGE_S:
            group.status = "worsening"
        else:
            group.status = "stable"

    group.early_line = _line([(float(run.avg_hr), run.pace_s_per_km) for run in early])
    group.recent_line = _line([(float(run.avg_hr), run.pace_s_per_km) for run in recent])
    group.confidence_score, group.reasons = _group_confidence(group)
    return group


def _group_out(group: GroupedRuns) -> PaceHrGroupOut:
    return PaceHrGroupOut(
        key=group.key,
        distance_band=group.distance_band,
        terrain_band=group.terrain_band,
        sessions=len(group.runs),
        start=group.runs[0].local_date,
        end=group.runs[-1].local_date,
        reference_hr=group.reference_hr,
        hr_min=min(run.avg_hr for run in group.runs),
        hr_max=max(run.avg_hr for run in group.runs),
        early_pace_s_per_km=group.early_pace,
        recent_pace_s_per_km=group.recent_pace,
        change_s_per_km=group.change_s,
        change_pct=group.change_pct,
        status=group.status,
        confidence=confidence_label(group.confidence_score),
        confidence_score=group.confidence_score,
        reasons=group.reasons,
        points=[
            PaceHrPointOut(
                date=run.local_date,
                activity_id=run.activity_id,
                activity_name=run.name,
                avg_hr=run.avg_hr,
                pace_s_per_km=round(run.pace_s_per_km, 1),
                adjusted_pace_s_per_km=run.adjusted_pace_s_per_km,
                distance_m=round(run.distance_m, 1),
                elevation_gain_m=(
                    round(run.elevation_gain_m, 1) if run.elevation_gain_m is not None else None
                ),
                period=run.period,
            )
            for run in group.runs
        ],
        early_line=group.early_line,
        recent_line=group.recent_line,
    )


def build_pace_hr(
    db: Session,
    days: int = 180,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> PaceHrAnalysisOut:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()
    days = max(30, min(days, 730))
    start = today - timedelta(days=days - 1)

    ensure_efforts(db)
    overview = build_overview(db, reference)
    threshold = overview.fitness_anchor.pace_s_per_km if overview.fitness_anchor else None
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.sport == "running",
            Activity.start_time_utc
            >= datetime(start.year, start.month, start.day) - offset - timedelta(days=2),
            Activity.start_time_utc
            <= datetime(today.year, today.month, today.day) - offset + timedelta(days=1),
        )
        .order_by(Activity.start_time_utc)
    ).all()
    hr_reference = _hr_reference(rows)

    excluded_races = 0
    excluded_hard = 0
    excluded_missing_hr = 0
    grouped: dict[str, list[ComparableRun]] = {}
    for activity in rows:
        local = (as_utc(activity.start_time_utc) + offset).date()
        if not (start <= local <= today):
            continue
        if activity.sub_sport == "trail_running":
            continue
        if activity.avg_hr is None:
            excluded_missing_hr += 1
            continue
        if activity.is_race:
            excluded_races += 1
            continue
        if (
            activity.distance_m < MIN_DISTANCE_M
            or activity.duration_s < MIN_DURATION_S
            or activity.distance_m <= 0
            or activity.duration_s <= 0
        ):
            continue
        pace = activity.duration_s / (activity.distance_m / 1000.0)
        if not (PACE_MIN <= pace <= PACE_MAX):
            continue
        record = RunRecord(
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
        )
        if classify_run(record, threshold, hr_reference) == "hard":
            excluded_hard += 1
            continue
        distance_band = _distance_band(activity.distance_m)
        terrain_band = _terrain_band(activity)
        key = f"{distance_band}_{terrain_band}"
        grouped.setdefault(key, []).append(
            ComparableRun(
                activity_id=activity.id,
                name=activity.name,
                local_date=local,
                pace_s_per_km=round(pace, 1),
                avg_hr=activity.avg_hr,
                max_hr=activity.max_hr,
                distance_m=activity.distance_m,
                elevation_gain_m=activity.elevation_gain_m,
                distance_band=distance_band,
                terrain_band=terrain_band,
                group_key=key,
            )
        )

    groups = [
        _build_group(key, runs) for key, runs in grouped.items() if len(runs) >= MIN_GROUP_SESSIONS
    ]
    groups.sort(key=lambda group: (len(group.runs), group.confidence_score), reverse=True)
    primary = groups[0] if groups else None

    sessions = sum(len(runs) for runs in grouped.values())
    warnings: list[str] = []
    if not rows:
        warnings.append("no_running_activities")
    if excluded_missing_hr and sessions == 0:
        warnings.append("no_hr")
    if sessions == 0:
        warnings.append("no_comparable_sessions")
    elif sessions < MIN_CONFIDENT_SESSIONS:
        warnings.append("few_sessions")
    if primary is not None:
        span = (primary.runs[-1].local_date - primary.runs[0].local_date).days
        if span < MIN_SPAN_DAYS:
            warnings.append("short_span")
        if "narrow_hr_range" in primary.reasons:
            warnings.append("narrow_hr_range")
    elif sessions:
        warnings.append("no_comparable_group")

    if primary is None:
        status = "insufficient"
        conclusion = "insufficient_data"
    elif (
        len(primary.runs) >= MIN_CONFIDENT_SESSIONS
        and (primary.runs[-1].local_date - primary.runs[0].local_date).days >= MIN_SPAN_DAYS
    ):
        status = "ok"
        conclusion = {
            "improving": "faster_same_hr",
            "worsening": "slower_same_hr",
            "stable": "stable_same_hr",
        }.get(primary.status, "insufficient_data")
    else:
        status = "partial"
        conclusion = "provisional_same_hr"

    params: dict[str, float | int | str | None] = {
        "sessions": len(primary.runs) if primary else 0,
        "window_days": days,
        "delta_s": primary.change_s if primary else None,
        "delta_pct": primary.change_pct if primary else None,
        "reference_hr": primary.reference_hr if primary else None,
        "distance_band": primary.distance_band if primary else None,
        "terrain_band": primary.terrain_band if primary else None,
    }

    notes = [
        "pace_hr_is_observational",
        "same_distance_and_terrain",
        "hr_adjusted_line",
        "temperature_not_controlled",
        "load_is_estimated",
        "not_medical_advice",
    ]
    if excluded_races:
        notes.append("races_excluded")
    if excluded_hard:
        notes.append("hard_sessions_excluded")

    return PaceHrAnalysisOut(
        generated_at=reference,
        model_version=MODEL_VERSION,
        window_days=days,
        status=status,
        sessions=sessions,
        excluded_races=excluded_races,
        excluded_hard=excluded_hard,
        excluded_missing_hr=excluded_missing_hr,
        groups=[_group_out(group) for group in groups],
        primary_group=primary.key if primary else None,
        conclusion=conclusion,
        conclusion_params=params,
        warnings=warnings,
        notes=notes,
    )
