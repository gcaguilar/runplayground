"""Prediction models for M1.

Two numbers are produced for every standard distance:

* **Ceiling** — the fastest equivalent performance supported by a recent
  effort. It uses Riegel's equivalence and Daniels' VDOT model and keeps the
  faster result, so it answers "how fast could I be if the distance were not
  the limiter?".
* **Planning** — a weighted power-law curve fitted to the athlete's own
  efforts (``time = a * distance^b``). The exponent is shrunk towards the
  standard 1.06 when there are few points, and the 10K value is the canonical
  fitness anchor.

Everything here is pure math. Database access and provenance live in
``app.services.performance``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import fmean

from app.utils import as_utc, utcnow

MODEL_VERSION = "m1.0"

STANDARD_DISTANCES: tuple[tuple[str, float], ...] = (
    ("5k", 5000.0),
    ("10k", 10000.0),
    ("half_marathon", 21097.5),
    ("marathon", 42195.0),
)
DISTANCE_BY_KEY = {key: distance for key, distance in STANDARD_DISTANCES}

RIEGEL_EXPONENT = 1.06
EXPONENT_SHRINKAGE = 2.5
MIN_EXPONENT = 1.02
MAX_EXPONENT = 1.14
LOOKBACK_DAYS = 730
RECENT_DAYS = 365
RECENCY_HALF_LIFE_DAYS = 180.0
RACE_DISTANCE_TOLERANCE = 0.025
INTERVAL_80 = 1.2815515655446004  # two-sided 80% normal interval
MIN_EFFORT_DISTANCE_M = 1500.0
MAX_EFFORT_DISTANCE_M = 50000.0


@dataclass(frozen=True)
class Effort:
    """One best effort, enriched with the activity fields the models need."""

    activity_id: int
    activity_name: str
    start_time_utc: datetime
    distance_m: float
    duration_s: float
    method: str
    is_full_activity: bool
    is_race: bool
    has_gps: bool
    quality: float
    segment_start_s: float
    segment_end_s: float

    @property
    def age_days(self) -> float:
        return max(0.0, (as_utc(utcnow()) - as_utc(self.start_time_utc)).total_seconds() / 86400)

    @property
    def pace_s_per_km(self) -> float:
        return self.duration_s / (self.distance_m / 1000.0)


@dataclass
class ModelEstimate:
    time_s: float
    low_s: float
    high_s: float
    method: str
    source_efforts: list[Effort] = field(default_factory=list)
    sigma: float = 0.0
    detail: dict = field(default_factory=dict)


@dataclass
class Confidence:
    score: float
    label: str
    reasons: list[str]


def age_days(value: datetime, now: datetime | None = None) -> float:
    reference = as_utc(now or utcnow())
    return max(0.0, (reference - as_utc(value)).total_seconds() / 86400)


def recency_weight(value: datetime, now: datetime | None = None) -> float:
    return 0.5 ** (age_days(value, now) / RECENCY_HALF_LIFE_DAYS)


def round_prediction_time(seconds: float) -> float:
    """Round to 5 s: predictions should not pretend to be stopwatch-exact."""
    return float(max(5, round(seconds / 5.0) * 5))


def riegel_time(
    source_time_s: float,
    source_distance_m: float,
    target_distance_m: float,
    exponent: float = RIEGEL_EXPONENT,
) -> float:
    if source_time_s <= 0 or source_distance_m <= 0 or target_distance_m <= 0:
        raise ValueError("Distances and time must be positive")
    return source_time_s * (target_distance_m / source_distance_m) ** exponent


# ---------------------------------------------------------------------------
# Daniels / VDOT


def vo2_for_velocity(velocity_m_min: float) -> float:
    return -4.60 + 0.182258 * velocity_m_min + 0.000104 * velocity_m_min**2


def sustainable_fraction(time_min: float) -> float:
    return (
        0.8
        + 0.1894393 * math.exp(-0.012778 * time_min)
        + 0.2989558 * math.exp(-0.1932605 * time_min)
    )


def vdot_from_performance(distance_m: float, time_s: float) -> float:
    if distance_m <= 0 or time_s <= 0:
        raise ValueError("Distance and time must be positive")
    time_min = time_s / 60.0
    velocity = distance_m / time_min
    return vo2_for_velocity(velocity) / sustainable_fraction(time_min)


def vdot_equivalent_time(vdot: float, distance_m: float) -> float | None:
    """Invert Daniels' model with a bisection on time.

    ``vdot`` is fixed and both velocity and sustainable fraction depend on the
    time, so there is no closed form. Returns ``None`` when the request is
    outside a plausible running range.
    """

    if vdot <= 0 or distance_m <= 0:
        return None

    def difference(time_s: float) -> float:
        time_min = time_s / 60.0
        velocity = distance_m / time_min
        return vo2_for_velocity(velocity) / sustainable_fraction(time_min) - vdot

    low = max(120.0, distance_m / 8.0)  # 8 m/s upper bound (~2:05/km)
    high = max(low * 2, distance_m / 1.5)  # 1.5 m/s lower bound (~11:07/km)
    low_value = difference(low)
    high_value = difference(high)
    if low_value == 0:
        return low
    if low_value * high_value > 0:
        return None
    for _ in range(80):
        middle = (low + high) / 2
        value = difference(middle)
        if abs(value) < 1e-7:
            return middle
        if value * low_value > 0:
            low = middle
            low_value = value
        else:
            high = middle
    return (low + high) / 2


# ---------------------------------------------------------------------------
# Estimates


def ceiling_estimate(
    efforts: list[Effort],
    target_distance_m: float,
    now: datetime | None = None,
) -> ModelEstimate | None:
    """Best equivalent performance, using Riegel and VDOT and keeping the faster.

    Only efforts from the last two years are passed in; a one-year old effort
    is still allowed, but it widens the range and lowers confidence elsewhere.
    """

    if not efforts:
        return None

    candidates: list[tuple[float, Effort, float, float]] = []
    for effort in efforts:
        riegel = riegel_time(effort.duration_s, effort.distance_m, target_distance_m)
        vdot = vdot_from_performance(effort.distance_m, effort.duration_s)
        equivalent = vdot_equivalent_time(vdot, target_distance_m)
        candidates.append(
            (riegel, effort, riegel, equivalent if equivalent is not None else riegel)
        )

    _best_riegel, source, riegel_value, vdot_value = min(
        candidates, key=lambda item: min(item[2], item[3])
    )
    best_time = min(riegel_value, vdot_value)
    method = "riegel" if riegel_value <= vdot_value else "vdot"

    distance_ratio = abs(math.log(target_distance_m / source.distance_m))
    base_sigma = 0.015 + (1.0 - max(0.0, min(1.0, source.quality))) * 0.035
    extrapolation_sigma = 0.030 * distance_ratio**1.2
    model_spread = abs(math.log(max(1e-6, riegel_value) / max(1e-6, vdot_value)))
    agreement_sigma = 0.35 * model_spread
    candidate_values = [min(item[2], item[3]) for item in candidates]
    dispersion = 0.0
    if len(candidate_values) >= 3:
        logs = [math.log(value) for value in candidate_values]
        mean_log = fmean(logs)
        dispersion = 0.25 * fmean(abs(value - mean_log) for value in logs)
    sigma = max(
        0.01,
        min(
            0.16,
            math.sqrt(base_sigma**2 + extrapolation_sigma**2 + agreement_sigma**2 + dispersion**2),
        ),
    )
    time_s = round_prediction_time(best_time)
    return ModelEstimate(
        time_s=time_s,
        low_s=round_prediction_time(best_time * math.exp(-INTERVAL_80 * sigma)),
        high_s=round_prediction_time(best_time * math.exp(INTERVAL_80 * sigma)),
        method=method,
        source_efforts=[source],
        sigma=sigma,
        detail={
            "riegel_s": round(riegel_value, 1),
            "vdot_s": round(vdot_value, 1),
            "model_spread_pct": round(model_spread * 100, 1),
            "source_distance_m": source.distance_m,
            "source_age_days": round(age_days(source.start_time_utc, now), 1),
        },
    )


def curve_estimate(
    efforts: list[Effort],
    target_distance_m: float,
    now: datetime | None = None,
) -> ModelEstimate | None:
    """Weighted log-log fit of the athlete's own distance profile."""

    usable = [
        effort
        for effort in efforts
        if MIN_EFFORT_DISTANCE_M <= effort.distance_m <= MAX_EFFORT_DISTANCE_M
        and effort.duration_s > 0
    ]
    if not usable:
        return None

    weights: list[float] = []
    xs: list[float] = []
    ys: list[float] = []
    for effort in usable:
        kind_weight = 1.15 if effort.is_race and effort.is_full_activity else 1.0
        if not effort.is_full_activity:
            kind_weight *= 0.8
        if not effort.is_race:
            kind_weight *= 0.9
        quality = max(0.0, min(1.0, effort.quality))
        weight = recency_weight(effort.start_time_utc, now) * quality * kind_weight
        if weight <= 0:
            continue
        weights.append(weight)
        xs.append(math.log(effort.distance_m))
        ys.append(math.log(effort.duration_s))

    if not weights:
        return None

    total_weight = sum(weights)
    mean_x = sum(weight * x for weight, x in zip(weights, xs, strict=True)) / total_weight
    mean_y = sum(weight * y for weight, y in zip(weights, ys, strict=True)) / total_weight
    variance_x = (
        sum(weight * (x - mean_x) ** 2 for weight, x in zip(weights, xs, strict=True))
        / total_weight
    )
    covariance = (
        sum(
            weight * (x - mean_x) * (y - mean_y)
            for weight, x, y in zip(weights, xs, ys, strict=True)
        )
        / total_weight
    )
    effective_n = total_weight**2 / sum(weight**2 for weight in weights)

    fitted_exponent = covariance / variance_x if variance_x > 0.015 else RIEGEL_EXPONENT
    clamped = min(MAX_EXPONENT, max(MIN_EXPONENT, fitted_exponent))
    exponent = (effective_n * clamped + EXPONENT_SHRINKAGE * RIEGEL_EXPONENT) / (
        effective_n + EXPONENT_SHRINKAGE
    )
    intercept = mean_y - exponent * mean_x

    residuals = [y - (intercept + exponent * x) for x, y in zip(xs, ys, strict=True)]
    residual_sigma = math.sqrt(
        sum(weight * residual**2 for weight, residual in zip(weights, residuals, strict=True))
        / total_weight
    )
    if effective_n <= 2:
        residual_sigma = 0.0

    nearest_delta = min(abs(math.log(target_distance_m / effort.distance_m)) for effort in usable)
    extrapolation_sigma = 0.028 * nearest_delta**1.15
    weighted_quality = (
        sum(weight * effort.quality for weight, effort in zip(weights, usable, strict=True))
        / total_weight
    )
    base_sigma = 0.018 + (1.0 - max(0.0, min(1.0, weighted_quality))) * 0.03
    if effective_n < 2:
        base_sigma += 0.02
    sigma = max(
        0.01, min(0.18, math.sqrt(base_sigma**2 + residual_sigma**2 + extrapolation_sigma**2))
    )

    predicted = math.exp(intercept + exponent * math.log(target_distance_m))
    source_efforts = sorted(
        usable,
        key=lambda effort: abs(math.log(target_distance_m / effort.distance_m)),
    )[:3]
    return ModelEstimate(
        time_s=round_prediction_time(predicted),
        low_s=round_prediction_time(predicted * math.exp(-INTERVAL_80 * sigma)),
        high_s=round_prediction_time(predicted * math.exp(INTERVAL_80 * sigma)),
        method="distance_curve",
        source_efforts=source_efforts,
        sigma=sigma,
        detail={
            "exponent": round(exponent, 4),
            "fitted_exponent": round(fitted_exponent, 4),
            "exponent_clamped": fitted_exponent != clamped,
            "effective_n": round(effective_n, 2),
            "residual_pct": round(residual_sigma * 100, 2),
            "nearest_distance_pct": round((math.exp(nearest_delta) - 1) * 100, 1),
            "weighted_quality": round(weighted_quality, 2),
            "efforts_used": len(usable),
        },
    )


def confidence_for(
    ceiling: ModelEstimate | None,
    curve: ModelEstimate | None,
    efforts: list[Effort],
    target_distance_m: float,
    *,
    longest_run_m: float | None = None,
    has_race_at_distance: bool = False,
    now: datetime | None = None,
) -> Confidence:
    if not efforts or ceiling is None or curve is None:
        return Confidence(0.0, "low", ["no_data"])

    reasons: list[str] = []
    score = 0.88
    effective_n = float(curve.detail.get("effective_n", 1))
    nearest_pct = float(curve.detail.get("nearest_distance_pct", 100)) / 100
    weighted_quality = float(curve.detail.get("weighted_quality", 0.5))
    newest_age = min(age_days(effort.start_time_utc, now) for effort in efforts)
    gap_pct = abs(curve.time_s - ceiling.time_s) / max(1.0, ceiling.time_s)

    if effective_n < 1.5:
        score -= 0.22
        reasons.append("single_effort")
    elif effective_n < 3:
        score -= 0.12
        reasons.append("few_efforts")

    if nearest_pct > 0.30:
        score -= 0.14
        reasons.append("extrapolated")
    elif nearest_pct > 0.15:
        score -= 0.06
        reasons.append("weak_distance_coverage")

    if newest_age > RECENT_DAYS:
        score -= 0.16
        reasons.append("stale_efforts")
    elif newest_age > 180:
        score -= 0.07
        reasons.append("aging_efforts")

    if weighted_quality < 0.65:
        score -= 0.10
        reasons.append("low_quality_streams")

    if gap_pct > 0.08:
        score -= 0.12
        reasons.append("model_disagreement")
    elif gap_pct > 0.04:
        score -= 0.05
        reasons.append("model_gap")

    if target_distance_m >= DISTANCE_BY_KEY["half_marathon"]:
        ratio = (longest_run_m or 0.0) / target_distance_m
        if ratio < 0.5:
            score -= 0.15
            reasons.append("no_long_run")
        elif ratio < 0.75:
            score -= 0.07
            reasons.append("short_long_run")

    if not has_race_at_distance:
        score -= 0.04
        reasons.append("no_race_at_distance")
    else:
        reasons.append("race_at_distance")

    if gap_pct <= 0.02 and effective_n >= 3:
        score += 0.04
        reasons.append("consistent_models")
    if effective_n >= 4 and weighted_quality >= 0.8:
        score += 0.03

    score = round(max(0.05, min(0.97, score)), 2)
    label = "high" if score >= 0.78 else "medium" if score >= 0.55 else "low"
    return Confidence(score, label, reasons)


def gap_seconds(
    ceiling: ModelEstimate | None, curve: ModelEstimate | None
) -> tuple[float | None, float | None]:
    if ceiling is None or curve is None:
        return None, None
    gap = curve.time_s - ceiling.time_s
    return round(gap, 1), round(gap / max(1.0, ceiling.time_s) * 100, 1)


def within_race_tolerance(distance_m: float, target_distance_m: float) -> bool:
    return abs(distance_m - target_distance_m) / target_distance_m <= RACE_DISTANCE_TOLERANCE


def recent_cutoff(now: datetime | None = None) -> datetime:
    return (now or utcnow()) - timedelta(days=RECENT_DAYS)


def lookback_cutoff(now: datetime | None = None) -> datetime:
    return (now or utcnow()) - timedelta(days=LOOKBACK_DAYS)
