"""Pure M3 helpers: streaks, week bucketing and calendar layout."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.analysis import RunRecord
from app.services.progress import (
    _distance_key,
    _percent_change,
    _streaks,
    _weekly_series,
)
from app.utils import utcnow


def _record(day: date, distance_m: float = 8000.0) -> RunRecord:
    return RunRecord(
        activity_id=int(day.strftime("%Y%m%d")),
        start_time_utc=utcnow(),
        local_date=day,
        distance_m=distance_m,
        duration_s=distance_m / 3.0,
    )


def test_percent_change_handles_zero_and_growth():
    assert _percent_change(120, 100) == 20.0
    assert _percent_change(50, 100) == -50.0
    assert _percent_change(10, 0) is None
    assert _percent_change(0, 100) == -100.0


def test_distance_key_uses_standard_tolerance():
    assert _distance_key(5000) == "5k"
    assert _distance_key(5010) == "5k"
    assert _distance_key(42195) == "marathon"
    assert _distance_key(7000) is None


def test_streaks_track_current_and_longest_runs():
    today = date(2026, 10, 26)
    days = {today, today - timedelta(days=1), today - timedelta(days=2)}
    days |= {today - timedelta(days=10), today - timedelta(days=9)}
    current, longest = _streaks(days, today)
    assert current == 3
    assert longest == 3

    # A missed today should not break a streak that ended yesterday.
    assert _streaks(days - {today}, today) == (2, 2)
    assert _streaks(set(), today) == (0, 0)


def test_weekly_series_buckets_by_monday_and_fills_gaps():
    start = date(2026, 10, 5)  # Monday
    records = [
        _record(start, 5000),
        _record(start + timedelta(days=2), 5000),
        _record(start + timedelta(days=9), 10000),
    ]
    weeks = _weekly_series(records, start, start + timedelta(days=20), None)

    assert len(weeks) == 3
    assert weeks[0].week_start == start
    assert weeks[0].distance_m == 10000
    assert weeks[0].sessions == 2
    assert weeks[0].active_days == 2
    assert weeks[1].distance_m == 10000
    assert weeks[2].distance_m == 0
