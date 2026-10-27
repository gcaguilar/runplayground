"""Future scenarios (M4).

Scenarios are conditional simulations, not forecasts. Each one changes one
training assumption for the next 8 or 12 weeks and projects the same prediction
curve under a deliberately capped effect. The module never extrapolates a
linear improvement: effects are bounded by distance, scaled by the gap between
current training and the assumption, and widened by horizon uncertainty.

Everything is derived from the existing diagnostics and prediction models. No
scenario is persisted; the assumptions, evidence and confidence are returned
with every response so the UI can explain the numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, PlannedRace
from app.schemas import (
    ForecastBaselineOut,
    ForecastGoalOut,
    ForecastView,
    ScenarioOut,
    ScenarioProjectionOut,
)
from app.services.analysis import (
    LONG_RUN_TARGETS,
    RunRecord,
    clamp,
    confidence_label,
    summarize_load,
)
from app.services.diagnostics import build_diagnostics
from app.services.performance import build_overview, ensure_efforts, store_snapshot
from app.services.performance_models import (
    INTERVAL_80,
    STANDARD_DISTANCES,
    round_prediction_time,
)
from app.utils import as_utc, utcnow

MODEL_VERSION = "m4.0"
HORIZONS = (8, 12)
FOCUS_DEFAULT = "10k"

# Maximum modelled gain at 12 weeks, as a percentage of the current time. The
# numbers are intentionally small: no scenario may promise a race result. The
# consistency effect is the broadest, specificity is distance-dependent, and
# recovery only helps when the current load suggests fatigue.
MAX_EFFECT_PCT: dict[str, dict[str, float]] = {
    "consistency": {
        "5k": 1.5,
        "10k": 2.0,
        "half_marathon": 2.5,
        "marathon": 3.0,
    },
    "specificity": {
        "5k": 0.5,
        "10k": 1.5,
        "half_marathon": 3.0,
        "marathon": 4.5,
    },
    "recovery": {
        "5k": 0.5,
        "10k": 0.8,
        "half_marathon": 1.2,
        "marathon": 1.5,
    },
}
# Twelve weeks is not 1.5x eight weeks: adaptations flatten and the uncertainty
# grows faster than the central estimate.
HORIZON_FACTOR = {8: 0.75, 12: 1.0}
HORIZON_SIGMA = {8: 0.012, 12: 0.018}
SCENARIO_SIGMA = {
    "maintain": 0.0,
    "consistency": 0.012,
    "specificity": 0.018,
    "recovery": 0.022,
}
SCENARIO_KEYS = ("maintain", "consistency", "specificity", "recovery")
DISTANCE_KEYS = {key for key, _distance in STANDARD_DISTANCES}


@dataclass
class FocusTarget:
    distance_key: str
    distance_m: float
    source: str
    target_time_s: float | None = None
    target_date: date | None = None
    name: str | None = None


@dataclass
class TrainingState:
    weekly_avg_m: float
    recent_28_m: float
    longest_28_m: float
    active_weeks: int
    weeks: int
    runs_per_week: float
    consistency_score: float | None
    specificity_score: float | None
    recovery_score: float | None
    load_ratio: float | None
    load_status: str
    hard_sessions: int
    target_long_m: float
    sessions_28: int
    quality_share: float | None


def _distance_key(distance_m: float) -> str:
    for key, standard in STANDARD_DISTANCES:
        if abs(standard - distance_m) / standard <= 0.025:
            return key
    return FOCUS_DEFAULT


def _dimension_metrics(diagnostics, key: str) -> dict[str, float]:
    for dimension in diagnostics.dimensions:
        if dimension.key == key:
            return dimension.metrics
    return {}


def _dimension_score(diagnostics, key: str) -> float | None:
    for dimension in diagnostics.dimensions:
        if dimension.key == key:
            return dimension.score
    return None


def _training_state(db: Session, diagnostics, today: date, offset: timedelta) -> TrainingState:
    volume = _dimension_metrics(diagnostics, "volume")
    consistency = _dimension_metrics(diagnostics, "consistency")
    specificity = _dimension_metrics(diagnostics, "specificity")
    load = _dimension_metrics(diagnostics, "load")

    start = today - timedelta(days=27)
    recent = _recent_runs(db, start, today, offset)
    threshold = diagnostics.coverage.anchor_pace_s_per_km
    load_summary = summarize_load(recent, today, threshold)
    hard = int(specificity.get("hard_sessions", 0))
    sessions = len(recent)

    return TrainingState(
        weekly_avg_m=float(volume.get("weekly_avg_m", 0.0)),
        recent_28_m=float(volume.get("recent_28_m", 0.0)),
        longest_28_m=float(volume.get("longest_28_m", 0.0)),
        active_weeks=int(consistency.get("active_weeks", 0)),
        weeks=int(consistency.get("weeks", 0)),
        runs_per_week=float(consistency.get("runs_per_week", 0.0)),
        consistency_score=_dimension_score(diagnostics, "consistency"),
        specificity_score=_dimension_score(diagnostics, "specificity"),
        recovery_score=_dimension_score(diagnostics, "recovery"),
        load_ratio=load_summary.ratio if load_summary.ratio is not None else load.get("ratio"),
        load_status=diagnostics.load.status,
        hard_sessions=hard,
        target_long_m=float(specificity.get("target_long_m", 0.0)),
        sessions_28=sessions,
        quality_share=(hard / sessions) if sessions else None,
    )


def _recent_runs(db: Session, start: date, end: date, offset: timedelta) -> list[RunRecord]:
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
                )
            )
    return output


def _focus(
    db: Session,
    diagnostics,
    today: date,
) -> FocusTarget:
    goal = diagnostics.goal
    if goal is not None and goal.target_date is not None and goal.target_date >= today:
        return FocusTarget(
            distance_key=_distance_key(goal.distance_m),
            distance_m=goal.distance_m,
            source="goal",
            target_time_s=goal.target_time_s,
            target_date=goal.target_date,
            name=goal.race_name,
        )

    race = db.scalar(
        select(PlannedRace)
        .where(PlannedRace.status == "planned", PlannedRace.race_date >= today)
        .order_by(PlannedRace.race_date, PlannedRace.id)
    )
    if race is not None:
        return FocusTarget(
            distance_key=_distance_key(race.distance_m),
            distance_m=race.distance_m,
            source="race",
            target_time_s=race.goal_time_s,
            target_date=race.race_date,
            name=race.name,
        )

    if goal is not None:
        return FocusTarget(
            distance_key=_distance_key(goal.distance_m),
            distance_m=goal.distance_m,
            source="goal",
            target_time_s=goal.target_time_s,
            target_date=goal.target_date,
            name=goal.race_name,
        )
    return FocusTarget(
        distance_key=FOCUS_DEFAULT,
        distance_m=10000.0,
        source="default",
    )


def _goal_gap(
    predicted_s: float | None,
    target_s: float | None,
) -> tuple[float | None, float | None, str]:
    if predicted_s is None or target_s is None:
        return None, None, "unknown"
    gap = round(target_s - predicted_s, 1)
    gap_pct = round(gap / max(1.0, predicted_s) * 100.0, 1)
    if predicted_s <= target_s:
        status = "ahead"
    elif predicted_s <= target_s * 1.02:
        status = "close"
    else:
        status = "behind"
    return gap, gap_pct, status


def _consistency_gap(state: TrainingState) -> float:
    if state.consistency_score is None:
        return 0.45
    # Only a score below the "good" band leaves room for this scenario. A
    # consistent athlete still gets a small floor, not an invented jump.
    gap = clamp((70.0 - state.consistency_score) / 70.0, 0.0, 1.0)
    return max(0.10, gap)


def _specificity_gap(state: TrainingState, distance_key: str) -> float:
    target_long = LONG_RUN_TARGETS.get(
        next(distance for key, distance in STANDARD_DISTANCES if key == distance_key),
        12000.0,
    )
    long_gap = clamp(1.0 - state.longest_28_m / target_long, 0.0, 1.0)
    quality_gap = clamp(1.0 - state.hard_sessions / 4.0, 0.0, 1.0)
    volume_gap = 0.0
    if state.weekly_avg_m > 0:
        target_volume = max(state.weekly_avg_m * 1.10, 20000.0)
        volume_gap = clamp(1.0 - state.weekly_avg_m / target_volume, 0.0, 1.0)
    return 0.5 * long_gap + 0.3 * quality_gap + 0.2 * volume_gap


def _fatigue(state: TrainingState) -> float:
    ratio = state.load_ratio
    if state.load_status == "risk" or (ratio is not None and ratio > 1.30):
        return 1.0
    if state.load_status == "watch" or (ratio is not None and ratio > 1.15):
        return 0.55
    if state.recovery_score is not None and state.recovery_score < 50:
        return 0.55
    return 0.0


def _effect_pct(
    scenario: str,
    distance_key: str,
    weeks: int,
    state: TrainingState,
    focus_key: str,
) -> float:
    horizon = HORIZON_FACTOR[weeks]
    if scenario == "maintain":
        return 0.0
    if scenario == "consistency":
        return MAX_EFFECT_PCT["consistency"][distance_key] * _consistency_gap(state) * horizon
    if scenario == "specificity":
        gap = _specificity_gap(state, distance_key)
        effect = MAX_EFFECT_PCT["specificity"][distance_key] * gap * horizon
        if distance_key != focus_key:
            effect *= 0.20
        return effect
    fatigue = _fatigue(state)
    if fatigue > 0:
        return MAX_EFFECT_PCT["recovery"][distance_key] * fatigue * horizon
    # A deload without fatigue costs a little fitness. This is a negative
    # "gain", kept small and explicitly explained in the assumptions.
    penalty = {"5k": 0.2, "10k": 0.3, "half_marathon": 0.5, "marathon": 0.7}[distance_key]
    return -penalty * horizon


def _scenario_confidence(
    base_score: float,
    scenario: str,
    weeks: int,
    state: TrainingState,
    distance_key: str,
    focus_key: str,
) -> tuple[float, str, list[str]]:
    reasons: list[str] = ["simulation_not_forecast"]
    score = base_score - (0.04 if weeks == 8 else 0.08)
    if scenario == "consistency":
        score -= 0.06 if weeks == 8 else 0.10
        if state.consistency_score is None:
            score -= 0.08
            reasons.append("no_consistency_data")
        elif state.consistency_score >= 70:
            reasons.append("already_consistent")
    elif scenario == "specificity":
        score -= 0.08 if weeks == 8 else 0.12
        if distance_key != focus_key:
            score -= 0.05
            reasons.append("spillover_from_focus")
        if state.specificity_score is None:
            score -= 0.06
            reasons.append("no_specificity_data")
    elif scenario == "recovery":
        score -= 0.08 if weeks == 8 else 0.12
        if state.load_ratio is None and state.recovery_score is None:
            score -= 0.10
            reasons.append("no_load_data")
        elif _fatigue(state) <= 0:
            reasons.append("no_fatigue_to_recover")
    else:
        reasons.append("current_training_only")
    score = round(clamp(score, 0.05, 0.95), 2)
    return score, confidence_label(score), reasons


def _projection(
    *,
    distance_key: str,
    distance_m: float,
    baseline,
    effect_pct: float,
    sigma: float,
    confidence: str,
    confidence_score: float,
) -> ScenarioProjectionOut:
    if baseline is None:
        return ScenarioProjectionOut(
            distance_key=distance_key,
            distance_m=distance_m,
            confidence=confidence,
            confidence_score=confidence_score,
        )
    time_s = baseline.time_s * (1.0 - effect_pct / 100.0)
    sigma = max(0.01, min(0.30, baseline.sigma + sigma))
    low = time_s * math.exp(-INTERVAL_80 * sigma)
    high = time_s * math.exp(INTERVAL_80 * sigma)
    rounded = round_prediction_time(time_s)
    return ScenarioProjectionOut(
        distance_key=distance_key,
        distance_m=distance_m,
        time_s=rounded,
        low_s=round_prediction_time(low),
        high_s=round_prediction_time(high),
        pace_s_per_km=round(rounded / (distance_m / 1000.0), 1),
        delta_s=round(rounded - baseline.time_s, 1),
        delta_pct=round((rounded - baseline.time_s) / max(1.0, baseline.time_s) * 100.0, 1),
        confidence=confidence,
        confidence_score=confidence_score,
    )


def _baseline(overview) -> ForecastBaselineOut:
    anchor = overview.fitness_anchor
    distances: list[ScenarioProjectionOut] = []
    for item in overview.distances:
        if item.planning is None:
            distances.append(
                ScenarioProjectionOut(
                    distance_key=item.distance_key,
                    distance_m=item.distance_m,
                    confidence=item.confidence,
                    confidence_score=item.confidence_score,
                )
            )
            continue
        distances.append(
            ScenarioProjectionOut(
                distance_key=item.distance_key,
                distance_m=item.distance_m,
                time_s=item.planning.time_s,
                low_s=item.planning.low_s,
                high_s=item.planning.high_s,
                pace_s_per_km=item.planning.pace_s_per_km,
                delta_s=0.0,
                delta_pct=0.0,
                confidence=item.confidence,
                confidence_score=item.confidence_score,
            )
        )
    return ForecastBaselineOut(
        anchor_time_s=anchor.time_s if anchor else None,
        anchor_low_s=anchor.low_s if anchor else None,
        anchor_high_s=anchor.high_s if anchor else None,
        confidence=anchor.confidence if anchor else "low",
        confidence_score=anchor.confidence_score if anchor else 0.0,
        distances=distances,
    )


def _assumptions(scenario: str, state: TrainingState) -> list[str]:
    if scenario == "maintain":
        return ["current_training", "same_volume", "same_intensity"]
    if scenario == "consistency":
        return ["more_regular_weeks", "same_weekly_volume", "no_intensity_change"]
    if scenario == "specificity":
        return ["gradual_specific_build", "longer_specific_runs", "quality_sessions"]
    if _fatigue(state) > 0:
        return ["two_week_deload", "return_to_current_load", "recovery_first"]
    return ["two_week_deload", "return_to_current_load", "no_fatigue_detected"]


def _evidence(scenario: str, state: TrainingState) -> dict[str, float | int | str | bool | None]:
    if scenario == "consistency":
        return {
            "consistency_score": state.consistency_score,
            "active_weeks": state.active_weeks,
            "weeks": state.weeks,
            "runs_per_week": state.runs_per_week,
        }
    if scenario == "specificity":
        return {
            "specificity_score": state.specificity_score,
            "longest_28_m": state.longest_28_m,
            "target_long_m": state.target_long_m,
            "hard_sessions": state.hard_sessions,
            "weekly_avg_m": state.weekly_avg_m,
        }
    if scenario == "recovery":
        return {
            "load_ratio": state.load_ratio,
            "load_status": state.load_status,
            "recovery_score": state.recovery_score,
        }
    return {
        "weekly_avg_m": state.weekly_avg_m,
        "active_weeks": state.active_weeks,
        "runs_per_week": state.runs_per_week,
    }


def _scenario_notes(scenario: str, weeks: int, state: TrainingState) -> list[str]:
    notes = ["simulation_not_forecast", "capped_effect", "uncertainty_grows_with_horizon"]
    notes.append(f"horizon_{weeks}_weeks")
    if scenario == "recovery" and _fatigue(state) <= 0:
        notes.append("deload_can_reduce_fitness")
    if scenario == "specificity":
        notes.append("specificity_is_distance_dependent")
    return notes


def build_forecast(
    db: Session,
    weeks: int = 8,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> ForecastView:
    if weeks not in HORIZONS:
        raise ValueError("Unknown forecast horizon")
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()

    ensure_efforts(db)
    diagnostics = build_diagnostics(db, reference, tz_offset_minutes)
    overview = build_overview(db, reference)
    store_snapshot(db, overview)
    state = _training_state(db, diagnostics, today, offset)
    focus = _focus(db, diagnostics, today)
    focus_key = focus.distance_key
    focus_distance = focus.distance_m
    focus_source = focus.source

    baseline = _baseline(overview)
    baseline_by_key = {item.distance_key: item for item in baseline.distances}
    focus_baseline = baseline_by_key.get(focus_key)
    anchor = overview.fitness_anchor
    goal_gap, goal_gap_pct, goal_status = _goal_gap(
        focus_baseline.time_s if focus_baseline else None,
        focus.target_time_s,
    )
    goal = (
        ForecastGoalOut(
            distance_key=focus_key,
            distance_m=focus_distance,
            name=focus.name,
            source=focus.source,
            target_time_s=focus.target_time_s,
            target_date=focus.target_date,
            days_to_target=(focus.target_date - today).days if focus.target_date else None,
            baseline_gap_s=goal_gap,
            baseline_gap_pct=goal_gap_pct,
            baseline_status=goal_status,
        )
        if focus.target_time_s is not None
        else None
    )

    scenarios: list[ScenarioOut] = []
    base_score = anchor.confidence_score if anchor else 0.2
    for scenario in SCENARIO_KEYS:
        projections: list[ScenarioProjectionOut] = []
        for item in overview.distances:
            effect = _effect_pct(scenario, item.distance_key, weeks, state, focus_key)
            score, label, reasons = _scenario_confidence(
                item.confidence_score if item.planning is not None else base_score,
                scenario,
                weeks,
                state,
                item.distance_key,
                focus_key,
            )
            projections.append(
                _projection(
                    distance_key=item.distance_key,
                    distance_m=item.distance_m,
                    baseline=item.planning,
                    effect_pct=effect,
                    sigma=HORIZON_SIGMA[weeks] + SCENARIO_SIGMA[scenario],
                    confidence=label,
                    confidence_score=score,
                )
            )

        focus_projection = next(
            (item for item in projections if item.distance_key == focus_key),
            None,
        )
        focus_effect = _effect_pct(scenario, focus_key, weeks, state, focus_key)
        score, label, reasons = _scenario_confidence(
            focus_baseline.confidence_score if focus_baseline else base_score,
            scenario,
            weeks,
            state,
            focus_key,
            focus_key,
        )
        if focus_projection is not None:
            focus_projection.confidence = label
            focus_projection.confidence_score = score

        scenario_gap, scenario_gap_pct, scenario_goal_status = _goal_gap(
            focus_projection.time_s if focus_projection else None,
            focus.target_time_s,
        )
        scenarios.append(
            ScenarioOut(
                key=scenario,
                assumptions=_assumptions(scenario, state),
                evidence=_evidence(scenario, state),
                effect_pct=round(focus_effect, 1),
                anchor_time_s=focus_projection.time_s if focus_projection else None,
                anchor_low_s=focus_projection.low_s if focus_projection else None,
                anchor_high_s=focus_projection.high_s if focus_projection else None,
                delta_s=focus_projection.delta_s if focus_projection else None,
                delta_pct=focus_projection.delta_pct if focus_projection else None,
                goal_gap_s=scenario_gap,
                goal_gap_pct=scenario_gap_pct,
                goal_status=scenario_goal_status,
                confidence=label,
                confidence_score=score,
                confidence_reasons=reasons,
                notes=_scenario_notes(scenario, weeks, state),
                distances=projections,
            )
        )

    warnings: list[str] = []
    if anchor is None:
        warnings.append("no_anchor")
    if state.weekly_avg_m <= 0:
        warnings.append("no_recent_volume")
    if state.consistency_score is None:
        warnings.append("no_consistency_data")
    if state.load_ratio is None:
        warnings.append("no_load_data")
    if focus_source == "default":
        warnings.append("no_goal")
    if goal is not None and goal.days_to_target is not None and goal.days_to_target > weeks * 7:
        warnings.append("horizon_before_goal")

    status = "ok" if anchor is not None and focus_baseline and focus_baseline.time_s else "partial"
    if anchor is None:
        status = "insufficient"

    notes = [
        "simulation_not_forecast",
        "effects_are_capped",
        "training_assumptions_explicit",
        "not_medical_advice",
    ]
    if focus_source == "default":
        notes.append("focus_defaults_to_10k")

    return ForecastView(
        generated_at=reference,
        model_version=MODEL_VERSION,
        weeks=weeks,
        status=status,
        focus_distance_key=focus_key,
        focus_distance_m=focus_distance,
        focus_source=focus_source,
        goal=goal,
        baseline=baseline,
        scenarios=scenarios,
        training={
            "weekly_avg_m": round(state.weekly_avg_m, 1),
            "recent_28_m": round(state.recent_28_m, 1),
            "longest_28_m": round(state.longest_28_m, 1),
            "active_weeks": state.active_weeks,
            "weeks": state.weeks,
            "runs_per_week": round(state.runs_per_week, 2),
            "consistency_score": state.consistency_score,
            "specificity_score": state.specificity_score,
            "recovery_score": state.recovery_score,
            "load_ratio": round(state.load_ratio, 2) if state.load_ratio is not None else None,
            "sessions_28": state.sessions_28,
            "quality_share": round(state.quality_share, 3)
            if state.quality_share is not None
            else None,
        },
        warnings=warnings,
        notes=notes,
    )
