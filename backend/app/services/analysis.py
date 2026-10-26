"""Training diagnostics for M2.

The module is deliberately pure: it receives normalised run records and returns
scores, distributions and a conservative weekly plan. Database access and
provenance live in :mod:`app.services.diagnostics`.

Six dimensions are scored from 0 to 100:

* volume       — recent weekly distance and progression
* consistency  — how often the athlete runs and how long the gaps are
* intensity    — easy/moderate/hard balance against the 80/20 principle
* load         — acute vs. chronic load and week-to-week ramps
* recovery     — rest days and back-to-back hard days; Garmin readiness is context only
* specificity  — long runs and race-pace work for the current goal

Scores are explicit heuristics, not medical advice. Every result carries
reason codes so the UI can explain why a dimension is flagged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

MODEL_VERSION = "m2.0"

WINDOW_DAYS = 84
BASELINE_DAYS = 28
CONSISTENCY_DAYS = 56
WEEKS_IN_WINDOW = 12
WEEKS_IN_CONSISTENCY = 8

INTENSITY_KEYS = ("easy", "moderate", "hard")
INTENSITY_TARGETS: dict[str, tuple[float, float]] = {
    "easy": (0.75, 0.85),
    "moderate": (0.05, 0.15),
    "hard": (0.10, 0.20),
}

DIMENSION_WEIGHTS: dict[str, float] = {
    "volume": 0.15,
    "consistency": 0.15,
    "intensity": 0.20,
    "load": 0.20,
    "recovery": 0.15,
    "specificity": 0.15,
}

LONG_RUN_TARGETS: dict[float, float] = {
    5000.0: 12000.0,
    10000.0: 12000.0,
    21097.5: 16000.0,
    42195.0: 24000.0,
}

PHASE_FACTORS: dict[str, tuple[float, float]] = {
    "maintenance": (0.95, 1.10),
    "base": (1.00, 1.15),
    "build": (1.00, 1.10),
    "peak": (0.90, 1.00),
    "taper": (0.55, 0.70),
    "recovery": (0.50, 0.65),
}


@dataclass(frozen=True)
class RunRecord:
    """One running activity normalised for analysis."""

    activity_id: int
    start_time_utc: datetime
    local_date: date
    distance_m: float
    duration_s: float
    avg_hr: int | None = None
    max_hr: int | None = None
    is_race: bool = False
    sub_sport: str | None = None
    has_streams: bool = False

    @property
    def pace_s_per_km(self) -> float | None:
        if self.distance_m > 0 and self.duration_s > 0:
            return self.duration_s / (self.distance_m / 1000.0)
        return None

    @property
    def is_trail(self) -> bool:
        return self.sub_sport == "trail_running"


@dataclass
class IntensityBucket:
    key: str
    sessions: int = 0
    duration_s: float = 0.0
    distance_m: float = 0.0
    share: float = 0.0


@dataclass
class IntensitySummary:
    buckets: list[IntensityBucket]
    classified_sessions: int
    unknown_sessions: int
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class VolumeSummary:
    weekly_avg_m: float
    recent_28_m: float
    previous_28_m: float
    trend_pct: float | None
    longest_28_m: float
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class ConsistencySummary:
    active_weeks: int
    weeks: int
    runs_per_week: float
    longest_gap_days: int
    total_runs: int
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class WeeklyLoad:
    week_start: date
    distance_m: float
    duration_s: float
    load: float
    sessions: int


@dataclass
class LoadSummary:
    weekly: list[WeeklyLoad]
    acute_7d: float
    chronic_weekly: float
    ratio: float | None
    ramp_pct: float | None
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class RecoverySummary:
    rest_days_per_week: float
    back_to_back_hard: int
    longest_streak: int
    readiness: float | None
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class SpecificitySummary:
    goal_distance_m: float | None
    target_long_m: float
    longest_28_m: float
    long_runs: int
    hard_sessions: int
    has_goal_effort: bool
    score: float | None
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class Phase:
    key: str
    reason: str
    weeks_to_goal: int | None


@dataclass
class SessionSpec:
    type: str
    intensity: str
    priority: str
    duration_low_s: float | None
    duration_high_s: float | None
    distance_low_m: float | None
    distance_high_m: float | None
    purpose: str


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def status_for(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "strong"
    if score >= 65:
        return "ok"
    if score >= 45:
        return "watch"
    return "risk"


def confidence_label(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def classify_run(
    run: RunRecord,
    threshold_pace_s_per_km: float | None = None,
    hr_reference: float | None = None,
) -> str:
    """Classify a run as easy, moderate or hard.

    Pace relative to the 10K anchor is preferred because it is specific to the
    athlete and survives missing heart-rate data. Heart rate is the fallback.
    The classification uses the session average, so an interval session with
    long recoveries can look easier than its hardest block.
    """

    pace = run.pace_s_per_km
    if threshold_pace_s_per_km and pace:
        ratio = pace / threshold_pace_s_per_km
        if ratio <= 1.05:
            return "hard"
        if ratio <= 1.15:
            return "moderate"
        return "easy"
    if hr_reference and run.avg_hr:
        ratio = run.avg_hr / hr_reference
        if ratio >= 0.85:
            return "hard"
        if ratio >= 0.75:
            return "moderate"
        return "easy"
    return "unknown"


def summarize_intensity(
    runs: list[RunRecord],
    threshold_pace_s_per_km: float | None = None,
    hr_reference: float | None = None,
) -> IntensitySummary:
    buckets = {key: IntensityBucket(key=key) for key in INTENSITY_KEYS}
    unknown = 0
    for run in runs:
        key = classify_run(run, threshold_pace_s_per_km, hr_reference)
        if key == "unknown" or run.duration_s <= 0:
            unknown += 1
            continue
        bucket = buckets[key]
        bucket.sessions += 1
        bucket.duration_s += run.duration_s
        bucket.distance_m += run.distance_m

    total_duration = sum(bucket.duration_s for bucket in buckets.values())
    for bucket in buckets.values():
        bucket.share = round(bucket.duration_s / total_duration, 4) if total_duration else 0.0

    classified = sum(bucket.sessions for bucket in buckets.values())
    if classified == 0:
        return IntensitySummary(
            buckets=list(buckets.values()),
            classified_sessions=0,
            unknown_sessions=unknown,
            score=None,
            status="unknown",
            reasons=["no_intensity_data"],
        )

    easy = buckets["easy"].share
    moderate = buckets["moderate"].share
    hard = buckets["hard"].share

    easy_short = clamp((0.80 - easy) / 0.30, 0.0, 1.0)
    hard_short = clamp((0.12 - hard) / 0.12, 0.0, 1.0)
    moderate_excess = clamp((moderate - 0.15) / 0.15, 0.0, 1.0)
    hard_excess = clamp((hard - 0.25) / 0.15, 0.0, 1.0)

    score = 100.0
    score -= 40.0 * easy_short
    score -= 30.0 * hard_short
    score -= 20.0 * moderate_excess
    score -= 10.0 * hard_excess
    if hard < 0.05:
        score -= 10.0
    score = round(clamp(score, 0.0, 100.0), 1)

    reasons: list[str] = []
    if easy > 0.90 and hard < 0.05:
        reasons.append("too_much_easy")
    if hard > 0.30:
        reasons.append("too_much_hard")
    if moderate > 0.20:
        reasons.append("gray_zone")
    if easy < 0.75:
        reasons.append("little_easy")
    if hard < 0.08:
        reasons.append("little_hard")
    if 0.75 <= easy <= 0.85 and 0.08 <= hard <= 0.22:
        reasons.append("balanced")
    if not reasons:
        reasons.append("acceptable_distribution")

    return IntensitySummary(
        buckets=list(buckets.values()),
        classified_sessions=classified,
        unknown_sessions=unknown,
        score=score,
        status=status_for(score),
        reasons=reasons,
    )


def summarize_volume(runs: list[RunRecord], today: date) -> VolumeSummary:
    recent_start = today - timedelta(days=BASELINE_DAYS - 1)
    previous_end = recent_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=BASELINE_DAYS - 1)

    recent = [run for run in runs if recent_start <= run.local_date <= today]
    previous = [run for run in runs if previous_start <= run.local_date <= previous_end]

    recent_28 = round(sum(run.distance_m for run in recent), 1)
    previous_28 = round(sum(run.distance_m for run in previous), 1)
    weekly_avg = round(recent_28 / 4.0, 1)
    longest = round(max((run.distance_m for run in recent), default=0.0), 1)
    trend = round((recent_28 - previous_28) / previous_28 * 100, 1) if previous_28 > 0 else None

    if not runs:
        return VolumeSummary(
            weekly_avg_m=0.0,
            recent_28_m=0.0,
            previous_28_m=0.0,
            trend_pct=None,
            longest_28_m=0.0,
            score=None,
            status="unknown",
            reasons=["insufficient_volume"],
        )

    weekly_km = weekly_avg / 1000.0
    if weekly_km >= 40:
        score = 85.0
    elif weekly_km >= 30:
        score = 78.0
    elif weekly_km >= 20:
        score = 66.0
    elif weekly_km >= 12:
        score = 52.0
    elif weekly_km > 0:
        score = 36.0
    else:
        score = 10.0

    reasons: list[str] = []
    if recent_28 <= 0:
        reasons.append("no_recent_volume")
    elif weekly_km < 12:
        reasons.append("low_volume")
    elif weekly_km >= 20:
        reasons.append("volume_ok")

    if trend is not None:
        if trend > 50:
            score -= 18.0
            reasons.append("ramp_fast")
        elif trend > 30:
            score -= 10.0
            reasons.append("ramp_fast")
        elif trend > 15:
            score -= 3.0
        elif trend < -30:
            score -= 12.0
            reasons.append("volume_declining")
        elif trend < -15:
            score -= 5.0
            reasons.append("volume_declining")
        else:
            reasons.append("volume_stable")
    elif recent_28 > 0:
        score += 6.0
        reasons.append("starting_block")

    score = round(clamp(score, 0.0, 100.0), 1)
    return VolumeSummary(
        weekly_avg_m=weekly_avg,
        recent_28_m=recent_28,
        previous_28_m=previous_28,
        trend_pct=trend,
        longest_28_m=longest,
        score=score,
        status=status_for(score),
        reasons=reasons,
    )


def summarize_consistency(runs: list[RunRecord], today: date) -> ConsistencySummary:
    start = today - timedelta(days=CONSISTENCY_DAYS - 1)
    window = [run for run in runs if start <= run.local_date <= today]
    if not window:
        return ConsistencySummary(
            active_weeks=0,
            weeks=WEEKS_IN_CONSISTENCY,
            runs_per_week=0.0,
            longest_gap_days=CONSISTENCY_DAYS,
            total_runs=0,
            score=None,
            status="unknown",
            reasons=["insufficient_consistency"],
        )

    run_dates = sorted({run.local_date for run in window})
    week_starts = {week_start(day) for day in run_dates}
    current_week = week_start(today)
    expected_weeks = {current_week - timedelta(weeks=index) for index in range(8)}
    active_weeks = len(week_starts & expected_weeks)
    runs_per_week = round(len(window) / WEEKS_IN_CONSISTENCY, 2)

    gaps = [(right - left).days for left, right in zip(run_dates, run_dates[1:], strict=False)]
    recent_gap = (today - run_dates[-1]).days
    longest_gap = max(gaps + [recent_gap]) if gaps else recent_gap

    score = (
        (active_weeks / WEEKS_IN_CONSISTENCY) * 55.0
        + min(runs_per_week / 4.0, 1.0) * 35.0
        + (10.0 if longest_gap <= 7 else 0.0)
    )
    if longest_gap > 14:
        score -= 20.0
    elif longest_gap > 10:
        score -= 10.0
    elif longest_gap > 7:
        score -= 5.0
    score = round(clamp(score, 0.0, 100.0), 1)

    reasons: list[str] = []
    if active_weeks >= 7:
        reasons.append("consistent_weeks")
    else:
        reasons.append("missed_weeks")
    if runs_per_week >= 3:
        reasons.append("regular_frequency")
    elif runs_per_week < 2:
        reasons.append("few_runs")
    if longest_gap > 10:
        reasons.append("long_gap")
    if not reasons:
        reasons.append("acceptable_consistency")

    return ConsistencySummary(
        active_weeks=active_weeks,
        weeks=WEEKS_IN_CONSISTENCY,
        runs_per_week=runs_per_week,
        longest_gap_days=longest_gap,
        total_runs=len(window),
        score=score,
        status=status_for(score),
        reasons=reasons,
    )


def session_load(run: RunRecord, threshold_pace_s_per_km: float | None) -> float:
    """A transparent pace-weighted load: minutes × intensity².

    It is not Garmin's EPOC/load model. It exists to compare weeks against each
    other with the athlete's own data and is always labelled as an estimate.
    """

    factor = 1.0
    pace = run.pace_s_per_km
    if threshold_pace_s_per_km and pace:
        factor = clamp(threshold_pace_s_per_km / pace, 0.6, 1.7)
    return (run.duration_s / 60.0) * factor * factor


def summarize_load(
    runs: list[RunRecord],
    today: date,
    threshold_pace_s_per_km: float | None,
) -> LoadSummary:
    current_week = week_start(today)
    first_week = current_week - timedelta(weeks=WEEKS_IN_WINDOW - 1)
    weekly: list[WeeklyLoad] = [
        WeeklyLoad(
            week_start=first_week + timedelta(weeks=index),
            distance_m=0.0,
            duration_s=0.0,
            load=0.0,
            sessions=0,
        )
        for index in range(WEEKS_IN_WINDOW)
    ]

    daily_load: dict[date, float] = {}
    for run in runs:
        load = session_load(run, threshold_pace_s_per_km)
        daily_load[run.local_date] = daily_load.get(run.local_date, 0.0) + load
        index = (week_start(run.local_date) - first_week).days // 7
        if 0 <= index < len(weekly):
            point = weekly[index]
            point.distance_m += run.distance_m
            point.duration_s += run.duration_s
            point.load += load
            point.sessions += 1

    for point in weekly:
        point.distance_m = round(point.distance_m, 1)
        point.duration_s = round(point.duration_s, 1)
        point.load = round(point.load, 1)

    if not runs:
        return LoadSummary(
            weekly=weekly,
            acute_7d=0.0,
            chronic_weekly=0.0,
            ratio=None,
            ramp_pct=None,
            score=None,
            status="unknown",
            reasons=["no_load_data"],
        )

    acute_start = today - timedelta(days=6)
    chronic_start = today - timedelta(days=27)
    previous_start = today - timedelta(days=13)
    previous_end = today - timedelta(days=7)

    acute = round(sum(value for day, value in daily_load.items() if day >= acute_start), 1)
    chronic = round(
        sum(value for day, value in daily_load.items() if day >= chronic_start) / 4.0, 1
    )
    previous_7 = sum(
        value for day, value in daily_load.items() if previous_start <= day <= previous_end
    )

    ratio = round(acute / chronic, 2) if chronic > 0 else None
    ramp = round((acute - previous_7) / previous_7 * 100, 1) if previous_7 > 0 else None

    score = 100.0
    reasons: list[str] = []
    if ratio is not None:
        if ratio > 1.45:
            score -= 35.0
            reasons.append("load_spike")
        elif ratio > 1.30:
            score -= 18.0
            reasons.append("load_rising")
        elif ratio < 0.60:
            score -= 35.0
            reasons.append("load_low")
        elif ratio < 0.75:
            score -= 18.0
            reasons.append("load_falling")
        elif ratio < 0.85:
            score -= 6.0
        else:
            reasons.append("load_balanced")

    if ramp is not None:
        if ramp > 40:
            score -= 20.0
            reasons.append("ramp_fast")
        elif ramp > 25:
            score -= 10.0
            reasons.append("ramp_fast")
        elif ramp < -40:
            score -= 8.0
            reasons.append("ramp_drop")

    if chronic <= 0:
        score = 0.0
        reasons.append("no_load_data")
    score = round(clamp(score, 0.0, 100.0), 1)

    return LoadSummary(
        weekly=weekly,
        acute_7d=acute,
        chronic_weekly=chronic,
        ratio=ratio,
        ramp_pct=ramp,
        score=score,
        status=status_for(score),
        reasons=reasons or ["acceptable_load"],
    )


def summarize_recovery(
    runs: list[RunRecord],
    today: date,
    threshold_pace_s_per_km: float | None,
    hr_reference: float | None,
    readiness: float | None,
) -> RecoverySummary:
    start = today - timedelta(days=27)
    window = [run for run in runs if start <= run.local_date <= today]
    if not window:
        return RecoverySummary(
            rest_days_per_week=0.0,
            back_to_back_hard=0,
            longest_streak=0,
            readiness=readiness,
            score=None,
            status="unknown",
            reasons=["insufficient_recovery"],
        )

    run_dates = sorted({run.local_date for run in window})
    rest_days = max(0, BASELINE_DAYS - len(run_dates))
    rest_days_per_week = round(rest_days / 4.0, 2)

    hard_dates = {
        run.local_date
        for run in window
        if classify_run(run, threshold_pace_s_per_km, hr_reference) == "hard"
    }
    back_to_back = sum(1 for day in hard_dates if day + timedelta(days=1) in hard_dates)

    longest_streak = 1
    streak = 1
    for left, right in zip(run_dates, run_dates[1:], strict=False):
        if (right - left).days == 1:
            streak += 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 1

    score = 100.0
    reasons: list[str] = []
    if rest_days_per_week < 1.0:
        score -= 25.0
        reasons.append("few_rest_days")
    elif rest_days_per_week < 1.5:
        score -= 12.0
        reasons.append("few_rest_days")
    else:
        reasons.append("rest_ok")

    if back_to_back >= 2:
        score -= 20.0
        reasons.append("back_to_back_hard")
    elif back_to_back == 1:
        score -= 10.0
        reasons.append("back_to_back_hard")

    if longest_streak >= 10:
        score -= 20.0
        reasons.append("long_streak")
    elif longest_streak >= 7:
        score -= 10.0
        reasons.append("long_streak")

    # Garmin readiness is external reference context. It is returned for the
    # recovery card but deliberately does not change the score or the plan.
    score = round(clamp(score, 0.0, 100.0), 1)
    return RecoverySummary(
        rest_days_per_week=rest_days_per_week,
        back_to_back_hard=back_to_back,
        longest_streak=longest_streak,
        readiness=readiness,
        score=score,
        status=status_for(score),
        reasons=reasons,
    )


def summarize_specificity(
    runs: list[RunRecord],
    today: date,
    goal_distance_m: float | None,
    has_goal_effort: bool,
    threshold_pace_s_per_km: float | None,
    hr_reference: float | None,
) -> SpecificitySummary:
    start = today - timedelta(days=BASELINE_DAYS - 1)
    recent = [run for run in runs if start <= run.local_date <= today]
    target_long = LONG_RUN_TARGETS.get(goal_distance_m or 0.0, 12000.0)
    longest = round(max((run.distance_m for run in recent), default=0.0), 1)
    long_runs = sum(1 for run in recent if run.distance_m >= target_long * 0.8)
    hard_sessions = sum(
        1
        for run in recent
        if classify_run(run, threshold_pace_s_per_km, hr_reference) == "hard"
        and (run.duration_s >= 600 or run.distance_m >= 3000)
    )

    if not runs:
        return SpecificitySummary(
            goal_distance_m=goal_distance_m,
            target_long_m=target_long,
            longest_28_m=0.0,
            long_runs=0,
            hard_sessions=0,
            has_goal_effort=has_goal_effort,
            score=None,
            status="unknown",
            reasons=["insufficient_specificity"],
        )

    score = 55.0 * min(longest / target_long, 1.0)
    score += 30.0 * min(hard_sessions / 4.0, 1.0)
    if has_goal_effort:
        score += 15.0
    elif goal_distance_m is not None:
        score += 8.0
    else:
        score += 10.0
    score = round(clamp(score, 0.0, 100.0), 1)

    reasons: list[str] = []
    if longest >= target_long:
        reasons.append("long_run_ok")
    elif longest >= target_long * 0.7:
        reasons.append("long_run_short")
    else:
        reasons.append("no_long_run")

    if hard_sessions >= 3:
        reasons.append("quality_ok")
    elif hard_sessions >= 1:
        reasons.append("little_quality")
    else:
        reasons.append("no_quality")

    if has_goal_effort:
        reasons.append("race_specific")
    elif goal_distance_m is not None:
        reasons.append("no_goal_effort")
    else:
        reasons.append("no_goal")

    return SpecificitySummary(
        goal_distance_m=goal_distance_m,
        target_long_m=target_long,
        longest_28_m=longest,
        long_runs=long_runs,
        hard_sessions=hard_sessions,
        has_goal_effort=has_goal_effort,
        score=score,
        status=status_for(score),
        reasons=reasons,
    )


def select_phase(
    today: date,
    goal_date: date | None,
    last_race_date: date | None,
) -> Phase:
    if goal_date is not None:
        days = (goal_date - today).days
        if days >= 0:
            weeks = int(math.ceil(days / 7.0))
            if weeks <= 2:
                return Phase("taper", "goal_taper", weeks)
            if weeks <= 6:
                return Phase("peak", "goal_peak", weeks)
            if weeks <= 14:
                return Phase("build", "goal_build", weeks)
            return Phase("base", "goal_base", weeks)

    if last_race_date is not None and (today - last_race_date).days <= 14:
        return Phase("recovery", "recent_race", None)
    return Phase("maintenance", "no_goal", None)


def target_weekly_distance(
    phase: str,
    base_weekly_m: float,
    reduce_for_load: bool = False,
) -> tuple[float, float]:
    if base_weekly_m <= 0:
        if phase == "recovery":
            return 8000.0, 14000.0
        return 12000.0, 20000.0

    low_factor, high_factor = PHASE_FACTORS.get(phase, PHASE_FACTORS["maintenance"])
    if reduce_for_load:
        low_factor *= 0.90
        high_factor *= 0.90
    low = max(8000.0, base_weekly_m * low_factor)
    high = max(low + 2000.0, base_weekly_m * high_factor)
    return round(low / 500.0) * 500.0, round(high / 500.0) * 500.0


def long_run_target(weekly_low_m: float, weekly_high_m: float) -> tuple[float, float]:
    weekly = (weekly_low_m + weekly_high_m) / 2.0
    low = clamp(weekly * 0.26, 8000.0, 24000.0)
    high = clamp(weekly * 0.32, 10000.0, 30000.0)
    return round(low / 500.0) * 500.0, round(high / 500.0) * 500.0


def _session(
    type_: str,
    intensity: str,
    priority: str,
    distance_low_m: float,
    distance_high_m: float,
    pace_s_per_km: float,
    purpose: str,
) -> SessionSpec:
    low = round(distance_low_m / 1000.0 * pace_s_per_km, 1)
    high = round(distance_high_m / 1000.0 * pace_s_per_km, 1)
    return SessionSpec(
        type=type_,
        intensity=intensity,
        priority=priority,
        duration_low_s=low,
        duration_high_s=high,
        distance_low_m=round(distance_low_m, 1),
        distance_high_m=round(distance_high_m, 1),
        purpose=purpose,
    )


def _rest() -> SessionSpec:
    return SessionSpec(
        type="rest",
        intensity="rest",
        priority="key",
        duration_low_s=None,
        duration_high_s=None,
        distance_low_m=None,
        distance_high_m=None,
        purpose="rest",
    )


def build_sessions(
    phase: str,
    weekly_low_m: float,
    weekly_high_m: float,
    threshold_pace_s_per_km: float | None,
    goal_pace_s_per_km: float | None,
    avoid_quality: bool = False,
) -> list[SessionSpec]:
    weekly = (weekly_low_m + weekly_high_m) / 2.0
    threshold = threshold_pace_s_per_km or 360.0
    easy_pace = threshold * 1.22
    session_pace = threshold * 1.08
    goal_pace = (goal_pace_s_per_km or threshold) * 1.06

    easy_low = clamp(weekly * 0.17, 4000.0, 12000.0)
    easy_high = clamp(weekly * 0.21, 5000.0, 14000.0)
    long_low = clamp(weekly * 0.27, 8000.0, 24000.0)
    long_high = clamp(weekly * 0.32, 10000.0, 30000.0)
    threshold_low = clamp(weekly * 0.10, 6000.0, 14000.0)
    threshold_high = clamp(weekly * 0.13, 8000.0, 16000.0)
    race_low = clamp(weekly * 0.09, 5000.0, 14000.0)
    race_high = clamp(weekly * 0.12, 7000.0, 16000.0)
    strides_low = clamp(weekly * 0.11, 4000.0, 10000.0)
    strides_high = clamp(weekly * 0.14, 5000.0, 12000.0)
    recovery_low = clamp(weekly * 0.08, 3000.0, 8000.0)
    recovery_high = clamp(weekly * 0.11, 4000.0, 10000.0)

    easy = lambda: _session(  # noqa: E731
        "easy", "easy", "support", easy_low, easy_high, easy_pace, "aerobic_base"
    )
    recovery = lambda: _session(  # noqa: E731
        "recovery", "easy", "optional", recovery_low, recovery_high, easy_pace, "recovery"
    )
    strides = lambda: _session(  # noqa: E731
        "strides",
        "moderate",
        "optional",
        strides_low,
        strides_high,
        easy_pace,
        "neuromuscular",
    )
    long_run = lambda: _session(  # noqa: E731
        "long", "easy", "key", long_low, long_high, easy_pace, "long_endurance"
    )
    threshold_session = lambda: _session(  # noqa: E731
        "threshold",
        "hard",
        "key",
        threshold_low,
        threshold_high,
        session_pace,
        "threshold",
    )
    race_pace = lambda: _session(  # noqa: E731
        "race_pace", "hard", "key", race_low, race_high, goal_pace, "race_specific"
    )

    if phase == "recovery" or avoid_quality:
        return [recovery(), easy(), _rest(), recovery(), easy(), _rest(), _rest()]

    if phase == "taper":
        return [
            easy(),
            race_pace(),
            easy(),
            _rest(),
            strides(),
            _rest(),
            _rest(),
        ]
    if phase == "peak":
        return [
            easy(),
            threshold_session(),
            race_pace(),
            easy(),
            long_run(),
            _rest(),
            _rest(),
        ]
    if phase == "build":
        return [
            easy(),
            threshold_session(),
            easy(),
            race_pace(),
            easy(),
            long_run(),
            _rest(),
        ]
    if phase == "base":
        return [
            easy(),
            strides(),
            easy(),
            threshold_session(),
            long_run(),
            _rest(),
            _rest(),
        ]
    return [
        easy(),
        strides(),
        easy(),
        threshold_session(),
        long_run(),
        _rest(),
        _rest(),
    ]
