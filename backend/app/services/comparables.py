"""Comparable pace–heart-rate analysis (M6, environmental context in M18).

The question is not "is my average pace better?" but "at the same heart rate
and in a comparable run, am I faster than before?". The service groups aerobic
runs by distance band and terrain, removes the within-group heart-rate effect
with a simple linear adjustment, and compares the earlier and later halves of
each group.

M18 adds an optional environmental correction. Elevation per kilometre yields
a conservative estimated terrain cost, and the mean temperature of the
activity's stream yields a capped heat cost. The headline early/recent change
uses the environment- plus heart-rate-adjusted pace; raw pace and the
heart-rate-only adjustment remain available for compatibility. Both
corrections are estimates and never raise confidence.

It is deliberately an association, not a physiological test. Groups need a
minimum of sessions and a minimum time span; if heart rate, elevation or the
number of comparable runs are missing, the response says so instead of
inventing a trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, StreamSample
from app.schemas import (
    PaceHrAnalysisOut,
    PaceHrGroupOut,
    PaceHrLineOut,
    PaceHrPointOut,
)
from app.services.analysis import RunRecord, clamp, classify_run, confidence_label
from app.services.analysis_settings import get_analysis_settings
from app.services.performance import build_overview, ensure_efforts
from app.utils import as_utc, utcnow

MODEL_VERSION = "m18.0"
MIN_DISTANCE_M = 4000.0
MIN_DURATION_S = 1200.0
MIN_GROUP_SESSIONS = 4
MIN_CONFIDENT_SESSIONS = 6
MIN_SPAN_DAYS = 28
STABLE_CHANGE_S = 1.5
PACE_MIN = 180.0
PACE_MAX = 900.0
# Terrain: a conservative linear cost of 1 s/km for every metre gained per km.
# Runs under 5 m/km are treated as flat and left uncorrected, matching the
# terrain bands. It is an estimate, capped so a bad elevation reading cannot
# dominate the pace.
TERRAIN_MIN_PER_KM = 5.0
TERRAIN_S_PER_KM_PER_M_PER_KM = 1.0
TERRAIN_ADJUSTMENT_CAP_S_PER_KM = 25.0
# Temperature: only stream averages within a plausible physiological range are
# used. Heat costs 0.3 % of pace per degree above 15 °C, capped at 6 %.
TEMPERATURE_MIN_C = -20.0
TEMPERATURE_MAX_C = 50.0
HEAT_BASELINE_C = 15.0
HEAT_PCT_PER_C = 0.003
HEAT_ADJUSTMENT_CAP_PCT = 0.06
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
    # Raw pace is the observed average. The environment-adjusted pace subtracts
    # the estimated terrain and heat costs; the HR-adjusted pace additionally
    # corrects to the group's reference heart rate.
    adjusted_pace_s_per_km: float | None = None
    elevation_per_km_m: float | None = None
    terrain_adjustment_s_per_km: float = 0.0
    temperature_c: float | None = None
    temperature_samples: int = 0
    heat_adjustment_s_per_km: float = 0.0
    environment_adjusted_pace_s_per_km: float | None = None
    environment_hr_adjusted_pace_s_per_km: float | None = None
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
    raw_early_pace: float | None = None
    raw_recent_pace: float | None = None
    environment_early_pace: float | None = None
    environment_recent_pace: float | None = None
    environment_change_s: float | None = None
    temperature_c: float | None = None
    temperature_sessions: int = 0
    temperature_coverage: float | None = None
    avg_elevation_per_km_m: float | None = None
    avg_terrain_adjustment_s_per_km: float | None = None
    avg_heat_adjustment_s_per_km: float | None = None
    terrain_adjusted: bool = False
    temperature_adjusted: bool = False
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


def _elevation_per_km(activity: Activity) -> float | None:
    if activity.elevation_gain_m is None or activity.distance_m <= 0:
        return None
    return float(activity.elevation_gain_m) / (activity.distance_m / 1000.0)


def _terrain_adjustment(elevation_per_km_m: float | None) -> float:
    """Estimated flat-equivalent saving in s/km for the gained elevation."""

    if elevation_per_km_m is None or elevation_per_km_m < TERRAIN_MIN_PER_KM:
        return 0.0
    raw = elevation_per_km_m * TERRAIN_S_PER_KM_PER_M_PER_KM
    return round(clamp(raw, 0.0, TERRAIN_ADJUSTMENT_CAP_S_PER_KM), 1)


def _heat_adjustment(pace_s_per_km: float, temperature_c: float | None) -> float:
    """Estimated flat/cool-equivalent saving in s/km for the heat cost."""

    if temperature_c is None or not (TEMPERATURE_MIN_C <= temperature_c <= TEMPERATURE_MAX_C):
        return 0.0
    excess = max(0.0, temperature_c - HEAT_BASELINE_C)
    fraction = min(excess * HEAT_PCT_PER_C, HEAT_ADJUSTMENT_CAP_PCT)
    return round(pace_s_per_km * fraction, 1)


def _temperatures_by_activity(
    db: Session, activity_ids: list[int]
) -> dict[int, tuple[float | None, int]]:
    """One aggregate query: mean and count of plausible stream temperatures.

    Reading every sample would make the endpoint proportional to the stream
    size. The database computes the per-activity mean instead, and the
    plausibility filter keeps implausible sensor readings out of the average.
    """

    if not activity_ids:
        return {}
    rows = db.execute(
        select(
            StreamSample.activity_id,
            func.avg(StreamSample.temperature_c),
            func.count(StreamSample.temperature_c),
        )
        .where(
            StreamSample.activity_id.in_(activity_ids),
            StreamSample.temperature_c.is_not(None),
            StreamSample.temperature_c >= TEMPERATURE_MIN_C,
            StreamSample.temperature_c <= TEMPERATURE_MAX_C,
        )
        .group_by(StreamSample.activity_id)
    ).all()
    return {
        int(activity_id): (float(average) if average is not None else None, int(count or 0))
        for activity_id, average, count in rows
    }


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
    missing_temperature = sum(1 for run in group.runs if run.temperature_c is None)
    if missing_temperature:
        reasons.append("temperature_not_available")
    if missing_temperature == sessions:
        # Backwards-compatible caveat, now only used when no stream carried a
        # plausible temperature.
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
    # Existing contract: raw pace adjusted for heart rate only.
    raw_slope, raw_intercept = _fit([(float(run.avg_hr), run.pace_s_per_km) for run in ordered])
    # Headline: environment-adjusted pace additionally corrected by heart rate.
    env_slope, env_intercept = _fit(
        [
            (float(run.avg_hr), run.environment_adjusted_pace_s_per_km or run.pace_s_per_km)
            for run in ordered
        ]
    )
    for run in ordered:
        if raw_slope is not None and raw_intercept is not None:
            run.adjusted_pace_s_per_km = round(
                run.pace_s_per_km - raw_slope * (run.avg_hr - reference_hr),
                1,
            )
        else:
            run.adjusted_pace_s_per_km = round(run.pace_s_per_km, 1)
        environment = run.environment_adjusted_pace_s_per_km or run.pace_s_per_km
        if env_slope is not None and env_intercept is not None:
            run.environment_hr_adjusted_pace_s_per_km = round(
                environment - env_slope * (run.avg_hr - reference_hr),
                1,
            )
        else:
            run.environment_hr_adjusted_pace_s_per_km = round(environment, 1)

    split = len(ordered) // 2
    early = ordered[:split]
    recent = ordered[split:]
    for run in early:
        run.period = "early"
    for run in recent:
        run.period = "recent"

    if len(early) >= 2 and len(recent) >= 2:
        group.raw_early_pace = round(median(run.pace_s_per_km for run in early), 1)
        group.raw_recent_pace = round(median(run.pace_s_per_km for run in recent), 1)
        group.environment_early_pace = round(
            median(run.environment_adjusted_pace_s_per_km or run.pace_s_per_km for run in early),
            1,
        )
        group.environment_recent_pace = round(
            median(run.environment_adjusted_pace_s_per_km or run.pace_s_per_km for run in recent),
            1,
        )
        group.environment_change_s = round(
            group.environment_recent_pace - group.environment_early_pace, 1
        )
        # The change uses the environment + heart-rate adjusted pace. A slow
        # session on a hot or hilly day should not read as lost fitness.
        group.early_pace = round(
            median(run.environment_hr_adjusted_pace_s_per_km or run.pace_s_per_km for run in early),
            1,
        )
        group.recent_pace = round(
            median(
                run.environment_hr_adjusted_pace_s_per_km or run.pace_s_per_km for run in recent
            ),
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

    temperatures = [run.temperature_c for run in ordered if run.temperature_c is not None]
    group.temperature_sessions = len(temperatures)
    group.temperature_c = round(sum(temperatures) / len(temperatures), 1) if temperatures else None
    group.temperature_coverage = round(len(temperatures) / len(ordered), 2) if ordered else None
    with_elevation = [run for run in ordered if run.elevation_per_km_m is not None]
    if with_elevation:
        group.avg_elevation_per_km_m = round(
            sum(run.elevation_per_km_m or 0.0 for run in with_elevation) / len(with_elevation),
            1,
        )
        group.avg_terrain_adjustment_s_per_km = round(
            sum(run.terrain_adjustment_s_per_km for run in with_elevation) / len(with_elevation),
            1,
        )
    if ordered:
        group.avg_heat_adjustment_s_per_km = round(
            sum(run.heat_adjustment_s_per_km for run in ordered) / len(ordered), 1
        )
    group.terrain_adjusted = bool(with_elevation) and any(
        run.terrain_adjustment_s_per_km > 0 for run in with_elevation
    )
    group.temperature_adjusted = any(run.heat_adjustment_s_per_km > 0 for run in ordered)

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
        raw_early_pace_s_per_km=group.raw_early_pace,
        raw_recent_pace_s_per_km=group.raw_recent_pace,
        environment_early_pace_s_per_km=group.environment_early_pace,
        environment_recent_pace_s_per_km=group.environment_recent_pace,
        environment_change_s_per_km=group.environment_change_s,
        temperature_c=group.temperature_c,
        temperature_sessions=group.temperature_sessions,
        temperature_coverage=group.temperature_coverage,
        avg_elevation_per_km_m=group.avg_elevation_per_km_m,
        avg_terrain_adjustment_s_per_km=group.avg_terrain_adjustment_s_per_km,
        avg_heat_adjustment_s_per_km=group.avg_heat_adjustment_s_per_km,
        terrain_adjusted=group.terrain_adjusted,
        temperature_adjusted=group.temperature_adjusted,
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
                environment_adjusted_pace_s_per_km=run.environment_adjusted_pace_s_per_km,
                environment_hr_adjusted_pace_s_per_km=(run.environment_hr_adjusted_pace_s_per_km),
                distance_m=round(run.distance_m, 1),
                elevation_gain_m=(
                    round(run.elevation_gain_m, 1) if run.elevation_gain_m is not None else None
                ),
                elevation_per_km_m=(
                    round(run.elevation_per_km_m, 1) if run.elevation_per_km_m is not None else None
                ),
                terrain_adjustment_s_per_km=run.terrain_adjustment_s_per_km,
                temperature_c=run.temperature_c,
                temperature_samples=run.temperature_samples,
                heat_adjustment_s_per_km=run.heat_adjustment_s_per_km,
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
    analysis = get_analysis_settings(db, reference, overview=overview)
    threshold = analysis.threshold_pace_s_per_km
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
    hr_reference = analysis.max_hr or _hr_reference(rows)

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
            intensity_override=activity.intensity_override,
            rpe=activity.rpe,
        )
        if (
            classify_run(
                record,
                threshold,
                hr_reference,
                mode=analysis.mode,
                threshold_hr=analysis.threshold_hr,
            )
            == "hard"
        ):
            excluded_hard += 1
            continue
        distance_band = _distance_band(activity.distance_m)
        terrain_band = _terrain_band(activity)
        elevation_per_km = _elevation_per_km(activity)
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
                elevation_per_km_m=elevation_per_km,
                terrain_adjustment_s_per_km=_terrain_adjustment(elevation_per_km),
            )
        )

    # Temperature is read once for every eligible activity, not sample by
    # sample. Activities without streams or without temperature stay at zero
    # adjustment and are reported as missing context.
    all_runs = [run for runs in grouped.values() for run in runs]
    temperatures = _temperatures_by_activity(db, [run.activity_id for run in all_runs])
    for run in all_runs:
        temperature, samples = temperatures.get(run.activity_id, (None, 0))
        run.temperature_c = round(temperature, 1) if temperature is not None else None
        run.temperature_samples = samples
        run.heat_adjustment_s_per_km = _heat_adjustment(run.pace_s_per_km, temperature)
        run.environment_adjusted_pace_s_per_km = round(
            run.pace_s_per_km - run.terrain_adjustment_s_per_km - run.heat_adjustment_s_per_km,
            1,
        )

    groups = [
        _build_group(key, runs) for key, runs in grouped.items() if len(runs) >= MIN_GROUP_SESSIONS
    ]
    groups.sort(key=lambda group: (len(group.runs), group.confidence_score), reverse=True)
    primary = groups[0] if groups else None

    sessions = sum(len(runs) for runs in grouped.values())
    all_eligible = [run for runs in grouped.values() for run in runs]
    temperature_values = [
        run.temperature_c for run in all_eligible if run.temperature_c is not None
    ]
    temperature_sessions = len(temperature_values)
    temperature_c = (
        round(sum(temperature_values) / len(temperature_values), 1) if temperature_values else None
    )
    temperature_coverage = round(temperature_sessions / sessions, 2) if sessions else None
    with_elevation = [run for run in all_eligible if run.elevation_per_km_m is not None]
    avg_elevation_per_km = (
        round(
            sum(run.elevation_per_km_m or 0.0 for run in with_elevation) / len(with_elevation),
            1,
        )
        if with_elevation
        else None
    )
    avg_terrain_adjustment = (
        round(
            sum(run.terrain_adjustment_s_per_km for run in with_elevation) / len(with_elevation),
            1,
        )
        if with_elevation
        else None
    )
    avg_heat_adjustment = (
        round(sum(run.heat_adjustment_s_per_km for run in all_eligible) / len(all_eligible), 1)
        if all_eligible
        else None
    )
    terrain_adjusted = bool(with_elevation) and any(
        run.terrain_adjustment_s_per_km > 0 for run in with_elevation
    )
    temperature_adjusted = any(run.heat_adjustment_s_per_km > 0 for run in all_eligible)

    warnings: list[str] = []
    if not rows:
        warnings.append("no_running_activities")
    if excluded_missing_hr and sessions == 0:
        warnings.append("no_hr")
    if sessions == 0:
        warnings.append("no_comparable_sessions")
    elif sessions < MIN_CONFIDENT_SESSIONS:
        warnings.append("few_sessions")
    if sessions and temperature_sessions == 0:
        warnings.append("temperature_not_available")
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
        "temperature_c": primary.temperature_c if primary else temperature_c,
        "avg_terrain_adjustment_s_per_km": (
            primary.avg_terrain_adjustment_s_per_km if primary else avg_terrain_adjustment
        ),
        "avg_heat_adjustment_s_per_km": (
            primary.avg_heat_adjustment_s_per_km if primary else avg_heat_adjustment
        ),
    }

    notes = [
        "pace_hr_is_observational",
        "same_distance_and_terrain",
        "hr_adjusted_line",
        "environment_adjusted_pace",
        "terrain_adjustment_estimated",
        "environment_context_only",
        "load_is_estimated",
        "not_medical_advice",
    ]
    if temperature_sessions:
        notes.append("temperature_from_streams")
    else:
        notes.append("temperature_not_available")
        notes.append("temperature_not_controlled")
    if temperature_adjusted:
        notes.append("heat_adjustment_applied")
    if excluded_races:
        notes.append("races_excluded")
    if excluded_hard:
        notes.append("hard_sessions_excluded")
    if analysis.has_manual:
        notes.append("manual_thresholds_applied")

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
        temperature_c=temperature_c,
        temperature_sessions=temperature_sessions,
        temperature_coverage=temperature_coverage,
        avg_elevation_per_km_m=avg_elevation_per_km,
        avg_terrain_adjustment_s_per_km=avg_terrain_adjustment,
        avg_heat_adjustment_s_per_km=avg_heat_adjustment,
        terrain_adjusted=terrain_adjusted,
        temperature_adjusted=temperature_adjusted,
        warnings=warnings,
        notes=notes,
    )
