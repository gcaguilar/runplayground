from __future__ import annotations

from datetime import date, datetime, time

from app.services.analysis import (
    RunRecord,
    classify_run,
    summarize_intensity,
    summarize_specificity,
)

TODAY = date(2026, 10, 26)
THRESHOLD_PACE = 300.0


def make_run(
    *,
    distance_km: float = 10.0,
    duration_min: float = 60.0,
    avg_hr: int | None = 150,
    max_hr: int | None = 185,
    intensity_override: str | None = None,
    day: date = TODAY,
) -> RunRecord:
    return RunRecord(
        activity_id=int(day.toordinal()),
        start_time_utc=datetime.combine(day, time(7, 0)),
        local_date=day,
        distance_m=distance_km * 1000,
        duration_s=duration_min * 60,
        avg_hr=avg_hr,
        max_hr=max_hr,
        intensity_override=intensity_override,
    )


def test_manual_override_wins_and_invalid_values_are_ignored():
    easy_with_hard_pace = make_run(duration_min=50, intensity_override="easy")
    hard_with_easy_pace = make_run(duration_min=75, intensity_override="hard")
    invalid = make_run(duration_min=50, intensity_override="sprint")

    assert classify_run(easy_with_hard_pace, THRESHOLD_PACE) == "easy"
    assert classify_run(hard_with_easy_pace, THRESHOLD_PACE) == "hard"
    assert classify_run(invalid, THRESHOLD_PACE) == "hard"


def test_classification_modes_respect_the_chosen_source():
    paced = make_run(duration_min=50, avg_hr=120)

    assert classify_run(paced, THRESHOLD_PACE, 190, mode="auto") == "hard"
    assert classify_run(paced, THRESHOLD_PACE, 190, mode="pace") == "hard"
    assert classify_run(paced, THRESHOLD_PACE, 190, mode="hr") == "easy"
    assert classify_run(paced, None, 190, mode="pace") == "unknown"
    assert classify_run(paced, None, 190, mode="auto") == "easy"


def test_threshold_hr_uses_tighter_cuts_than_max_hr():
    threshold_hr = 180
    max_hr = 200

    above_threshold = make_run(duration_min=70, avg_hr=172)
    upper_moderate = make_run(duration_min=70, avg_hr=155)
    easy = make_run(duration_min=70, avg_hr=140)

    assert classify_run(above_threshold, None, mode="hr", threshold_hr=threshold_hr) == "hard"
    assert classify_run(upper_moderate, None, mode="hr", threshold_hr=threshold_hr) == "moderate"
    assert classify_run(easy, None, mode="hr", threshold_hr=threshold_hr) == "easy"

    # Same heart rates on the max-HR scale are more conservative.
    assert classify_run(above_threshold, None, max_hr, mode="hr") == "hard"
    assert classify_run(upper_moderate, None, max_hr, mode="hr") == "moderate"
    assert classify_run(easy, None, max_hr, mode="hr") == "easy"

    between = make_run(duration_min=70, avg_hr=165)
    assert classify_run(between, None, mode="hr", threshold_hr=180) == "moderate"
    assert classify_run(between, None, 200, mode="hr") == "moderate"
    # A threshold HR (0.88 × max) is a tighter reference than the max HR.
    tight = make_run(duration_min=70, avg_hr=168)
    assert classify_run(tight, None, mode="hr", threshold_hr=176) == "hard"
    assert classify_run(tight, None, 200, mode="hr") == "moderate"


def test_override_changes_intensity_distribution_and_specificity():
    runs = [
        make_run(duration_min=50, day=TODAY),
        make_run(duration_min=52, day=TODAY),
        make_run(duration_min=55, day=TODAY),
        make_run(duration_min=75, day=TODAY),
    ]
    baseline = summarize_intensity(runs, THRESHOLD_PACE)
    assert baseline.buckets[2].sessions == 2

    overridden = [run for run in runs]
    overridden[0] = make_run(duration_min=50, intensity_override="easy", day=TODAY)
    after = summarize_intensity(overridden, THRESHOLD_PACE)
    assert after.buckets[2].sessions == 1
    assert after.buckets[0].sessions == 2

    specificity = summarize_specificity(
        overridden,
        TODAY,
        10000.0,
        False,
        THRESHOLD_PACE,
        190,
    )
    assert specificity.hard_sessions == 1
