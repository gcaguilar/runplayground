from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.services.analysis import (
    RunRecord,
    build_sessions,
    classify_run,
    select_phase,
    summarize_consistency,
    summarize_intensity,
    summarize_load,
    summarize_recovery,
    summarize_specificity,
    summarize_volume,
    target_weekly_distance,
)

TODAY = date(2026, 10, 26)
THRESHOLD = 300.0


def make_run(
    day: date,
    distance_km: float = 10.0,
    duration_min: float = 60.0,
    avg_hr: int | None = 150,
    max_hr: int | None = 185,
    is_race: bool = False,
    sub_sport: str | None = None,
) -> RunRecord:
    duration_s = duration_min * 60
    return RunRecord(
        activity_id=int(day.toordinal()),
        start_time_utc=datetime.combine(day, time(7, 0)),
        local_date=day,
        distance_m=distance_km * 1000,
        duration_s=duration_s,
        avg_hr=avg_hr,
        max_hr=max_hr,
        is_race=is_race,
        sub_sport=sub_sport,
    )


def test_classify_run_uses_pace_then_heart_rate():
    easy = make_run(TODAY, 10, 75)  # 7:30/km
    moderate = make_run(TODAY, 10, 55)  # 5:30/km
    hard = make_run(TODAY, 10, 50)  # 5:00/km

    assert classify_run(easy, THRESHOLD) == "easy"
    assert classify_run(moderate, THRESHOLD) == "moderate"
    assert classify_run(hard, THRESHOLD) == "hard"

    assert classify_run(make_run(TODAY, 10, 60, avg_hr=180), None, 190) == "hard"
    assert classify_run(make_run(TODAY, 10, 60, avg_hr=150), None, 190) == "moderate"
    assert classify_run(make_run(TODAY, 10, 60, avg_hr=130), None, 190) == "easy"
    assert classify_run(make_run(TODAY, 10, 60, avg_hr=None), None, None) == "unknown"


def test_intensity_distribution_and_gray_zone():
    runs = [make_run(TODAY - timedelta(days=index), 10, 75) for index in range(4)]
    runs += [make_run(TODAY - timedelta(days=10 + index), 10, 55) for index in range(4)]
    runs.append(make_run(TODAY - timedelta(days=20), 10, 50))

    summary = summarize_intensity(runs, THRESHOLD)

    assert summary.classified_sessions == 9
    assert summary.unknown_sessions == 0
    assert summary.buckets[0].share > 0.4
    assert "gray_zone" in summary.reasons
    assert summary.score is not None and summary.score < 90


def test_balanced_intensity_scores_well():
    runs = [make_run(TODAY - timedelta(days=index), 10, 75) for index in range(7)]
    runs.append(make_run(TODAY - timedelta(days=8), 10, 66.7))
    runs += [make_run(TODAY - timedelta(days=9 + index), 8, 40) for index in range(2)]

    summary = summarize_intensity(runs, THRESHOLD)

    assert summary.buckets[0].share > 0.75
    assert summary.buckets[2].share >= 0.10
    assert summary.score is not None and summary.score >= 80


def test_volume_detects_fast_ramp():
    previous = [make_run(TODAY - timedelta(days=35 + index), 10, 60) for index in range(10)]
    recent = [make_run(TODAY - timedelta(days=index), 14, 84) for index in range(10)]

    summary = summarize_volume(previous + recent, TODAY)

    assert summary.recent_28_m > summary.previous_28_m
    assert summary.trend_pct is not None and summary.trend_pct > 30
    assert "ramp_fast" in summary.reasons


def test_consistency_rewards_regular_runs():
    runs = [make_run(TODAY - timedelta(days=index * 3), 8, 48) for index in range(18)]

    summary = summarize_consistency(runs, TODAY)

    assert summary.active_weeks == 8
    assert summary.longest_gap_days <= 3
    assert summary.score is not None and summary.score >= 80


def test_load_flags_acute_spike():
    runs = [make_run(TODAY - timedelta(days=20 + index), 8, 48) for index in range(12)]
    runs += [make_run(TODAY - timedelta(days=index), 18, 108) for index in range(6)]

    summary = summarize_load(runs, TODAY, THRESHOLD)

    assert summary.ratio is not None and summary.ratio > 1.3
    assert "load_spike" in summary.reasons
    assert len(summary.weekly) == 12


def test_recovery_flags_daily_running_and_hard_days():
    runs = [make_run(TODAY - timedelta(days=index), 10, 50, avg_hr=175) for index in range(14)]

    summary = summarize_recovery(runs, TODAY, THRESHOLD, 190, 35)

    assert summary.rest_days_per_week == 3.5
    assert summary.longest_streak >= 10
    assert summary.back_to_back_hard > 0
    assert summary.readiness == 35
    assert summary.score is not None and summary.score < 65

    # Garmin readiness is reference context, not a scoring input.
    without_readiness = summarize_recovery(runs, TODAY, THRESHOLD, 190, None)
    assert summary.score == without_readiness.score
    assert summary.reasons == without_readiness.reasons


def test_specificity_uses_goal_distance():
    runs = [make_run(TODAY - timedelta(days=index * 4), 16, 96) for index in range(6)]
    runs += [make_run(TODAY - timedelta(days=10 + index * 5), 10, 50) for index in range(3)]

    half = summarize_specificity(runs, TODAY, 21097.5, False, THRESHOLD, 190)
    ten = summarize_specificity(runs, TODAY, 10000.0, True, THRESHOLD, 190)

    assert half.target_long_m == 16000
    assert "long_run_ok" in half.reasons
    assert ten.score is not None and half.score is not None
    assert ten.score > half.score
    assert "race_specific" in ten.reasons


def test_phase_selection_and_targets():
    assert select_phase(TODAY, TODAY + timedelta(weeks=1), None).key == "taper"
    assert select_phase(TODAY, TODAY + timedelta(weeks=4), None).key == "peak"
    assert select_phase(TODAY, TODAY + timedelta(weeks=10), None).key == "build"
    assert select_phase(TODAY, TODAY + timedelta(weeks=20), None).key == "base"
    assert select_phase(TODAY, None, TODAY - timedelta(days=5)).key == "recovery"
    assert select_phase(TODAY, None, None).key == "maintenance"

    low, high = target_weekly_distance("taper", 30000)
    assert low < 25000
    assert high <= 25000
    assert low < high


def test_sessions_follow_phase_and_recovery():
    taper = build_sessions("taper", 24000, 28000, THRESHOLD, 280)
    types = [session.type for session in taper]
    assert len(taper) == 7
    assert "race_pace" in types
    assert "rest" in types
    assert "long" not in types

    recovery = build_sessions(
        "recovery",
        12000,
        16000,
        THRESHOLD,
        None,
        avoid_quality=True,
    )
    recovery_types = [session.type for session in recovery]
    assert len(recovery) == 7
    assert "threshold" not in recovery_types
    assert "race_pace" not in recovery_types
    assert "rest" in recovery_types

    build = build_sessions("build", 30000, 36000, THRESHOLD, 280)
    build_types = [session.type for session in build]
    assert len(build) == 7
    assert "threshold" in build_types
    assert "race_pace" in build_types
    assert "long" in build_types
