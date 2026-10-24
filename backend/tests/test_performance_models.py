from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from app.services.efforts import best_segment, build_points, stream_quality
from app.services.performance_models import (
    Effort,
    ceiling_estimate,
    confidence_for,
    curve_estimate,
    gap_seconds,
    riegel_time,
    vdot_equivalent_time,
    vdot_from_performance,
    within_race_tolerance,
)

NOW = datetime(2026, 10, 24, 12, 0)


def make_effort(
    distance_m: float,
    duration_s: float,
    *,
    days_ago: float = 30,
    is_race: bool = True,
    quality: float = 0.95,
    full: bool = True,
    activity_id: int = 1,
) -> Effort:
    return Effort(
        activity_id=activity_id,
        activity_name=f"Effort {activity_id}",
        start_time_utc=NOW - timedelta(days=days_ago),
        distance_m=distance_m,
        duration_s=duration_s,
        method="activity" if full else "stream",
        is_full_activity=full,
        is_race=is_race,
        has_gps=True,
        quality=quality,
        segment_start_s=0.0,
        segment_end_s=duration_s,
    )


def test_riegel_equivalence_uses_standard_exponent():
    assert riegel_time(1200, 5000, 10000) == pytest.approx(1200 * 2**1.06)
    with pytest.raises(ValueError):
        riegel_time(0, 5000, 10000)


def test_vdot_round_trip_is_stable():
    vdot = vdot_from_performance(5000, 1200)
    assert 45 < vdot < 55
    recovered = vdot_equivalent_time(vdot, 5000)
    assert recovered == pytest.approx(1200, abs=0.5)
    assert vdot_equivalent_time(0, 5000) is None


def test_ceiling_uses_the_faster_of_riegel_and_vdot():
    effort = make_effort(5000, 1200)
    estimate = ceiling_estimate([effort], 10000, NOW)
    assert estimate is not None
    assert estimate.low_s < estimate.time_s < estimate.high_s
    assert estimate.method in {"riegel", "vdot"}
    assert estimate.detail["riegel_s"] > 0
    assert estimate.detail["vdot_s"] > 0
    assert estimate.time_s == pytest.approx(
        min(estimate.detail["riegel_s"], estimate.detail["vdot_s"]), abs=5
    )


def test_curve_with_one_effort_matches_riegel_and_is_monotonic():
    effort = make_effort(5000, 1200)
    five = curve_estimate([effort], 5000, NOW)
    ten = curve_estimate([effort], 10000, NOW)
    half = curve_estimate([effort], 21097.5, NOW)
    assert five and ten and half
    assert five.time_s == pytest.approx(1200, abs=5)
    assert five.time_s < ten.time_s < half.time_s
    assert ten.time_s == pytest.approx(riegel_time(1200, 5000, 10000), abs=5)
    assert ten.low_s < ten.time_s < ten.high_s


def test_curve_fits_at_athletes_own_exponent():
    five = make_effort(5000, 1200, activity_id=1)
    ten = make_effort(10000, 2520, activity_id=2)
    half = make_effort(21097.5, 5580, activity_id=3)
    estimate = curve_estimate([five, ten, half], 42195, NOW)
    assert estimate is not None
    exponent = estimate.detail["exponent"]
    assert 1.02 <= exponent <= 1.14
    assert estimate.detail["efforts_used"] == 3
    assert estimate.time_s > half.duration_s


def test_gap_is_zero_for_matching_models_and_positive_when_planning_is_slower():
    effort = make_effort(5000, 1200)
    ceiling = ceiling_estimate([effort], 10000, NOW)
    planning = curve_estimate([effort], 10000, NOW)
    gap_s, gap_pct = gap_seconds(ceiling, planning)
    assert gap_s is not None and gap_pct is not None
    assert gap_s == pytest.approx(planning.time_s - ceiling.time_s)
    assert gap_s >= 0
    assert gap_seconds(None, planning) == (None, None)


def test_confidence_drops_without_recent_quality_efforts():
    recent_race = make_effort(10000, 2520)
    old_training = make_effort(10000, 2700, days_ago=500, is_race=False, quality=0.5)
    strong = confidence_for(
        ceiling_estimate([recent_race], 10000, NOW),
        curve_estimate([recent_race], 10000, NOW),
        [recent_race],
        10000,
        longest_run_m=12000,
        has_race_at_distance=True,
        now=NOW,
    )
    weak = confidence_for(
        ceiling_estimate([old_training], 10000, NOW),
        curve_estimate([old_training], 10000, NOW),
        [old_training],
        10000,
        longest_run_m=6000,
        has_race_at_distance=False,
        now=NOW,
    )
    assert strong.score > weak.score
    assert "stale_efforts" in weak.reasons
    assert "low_quality_streams" in weak.reasons
    assert strong.label in {"medium", "high"}


def test_race_distance_tolerance():
    assert within_race_tolerance(5000, 5000)
    assert within_race_tolerance(5100, 5000)
    assert not within_race_tolerance(5300, 5000)


def test_best_segment_constant_pace():
    times = [float(second) for second in range(2401)]
    distances = [second / 2400 * 10000 for second in range(2401)]
    points = build_points(times, distances)
    five = best_segment(points, 5000)
    ten = best_segment(points, 10000)
    assert five is not None and five.duration_s == pytest.approx(1200, abs=0.1)
    assert ten is not None and ten.duration_s == pytest.approx(2400, abs=0.1)
    assert best_segment(points, 21097.5) is None


def test_best_segment_negative_split_picks_fast_half():
    times = [float(second) for second in range(2401)]
    distances = []
    for second in times:
        if second <= 1300:
            distances.append(second / 1300 * 5000)
        else:
            distances.append(5000 + (second - 1300) / 1100 * 5000)
    points = build_points(times, distances)
    five = best_segment(points, 5000)
    assert five is not None
    assert five.start_s == pytest.approx(1300, abs=1)
    assert five.duration_s == pytest.approx(1100, abs=1)


def test_build_points_survives_gps_noise_and_time_gaps():
    points = build_points(
        [0, 5, 5, 10, 15, 20],
        [0, 25, 27, 50, 48, 120],
    )
    assert points[0] == (0, 0)
    assert all(b[0] > a[0] for a, b in zip(points, points[1:], strict=False))
    assert all(b[1] >= a[1] for a, b in zip(points, points[1:], strict=False))
    assert points[-1][1] == pytest.approx(120)
    assert stream_quality(points, has_gps=True, has_hr=True, is_full_activity=True) > 0.8


def test_build_points_handles_empty_and_single_samples():
    assert build_points([], []) == []
    assert build_points([0], [0]) == [(0, 0)]
    assert math.isfinite(
        stream_quality([(0, 0)], has_gps=False, has_hr=False, is_full_activity=False)
    )
