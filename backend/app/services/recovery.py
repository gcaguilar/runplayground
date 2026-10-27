"""Recovery context from the Garmin data export (M9).

Sleep, HRV, resting heart rate, Body Battery and weight are imported as
``external_metrics`` and shown as context. They never change the fitness
anchor, the race predictions or the diagnostics score: the app cannot know
whether a bad night is noise, illness or a hard training block. Missing data
and stale exports stay visible instead of being filled in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExternalMetric
from app.schemas import RecoveryMetricOut, RecoveryMetricPointOut, RecoveryOverview
from app.utils import as_utc, utcnow

MODEL_VERSION = "m9.0"
GARMIN_SOURCE = "garmin_export"
DEFAULT_DAYS = 90
METRIC_UNITS: dict[str, str] = {
    "sleep_duration": "s",
    "sleep_score": "score",
    "hrv": "ms",
    "resting_hr": "bpm",
    "body_battery": "score",
    "weight": "kg",
}
CORE_METRICS = (
    "sleep_duration",
    "hrv",
    "resting_hr",
    "body_battery",
    "weight",
)
METRIC_WARNINGS = {
    "sleep_duration": "no_sleep_data",
    "sleep_score": "no_sleep_score_data",
    "hrv": "no_hrv_data",
    "resting_hr": "no_resting_hr_data",
    "body_battery": "no_body_battery_data",
    "weight": "no_weight_data",
}


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _metric(
    key: str,
    rows: list[ExternalMetric],
    today: date,
) -> RecoveryMetricOut:
    points = [
        RecoveryMetricPointOut(date=row.metric_date, value=round(row.value, 2))
        for row in sorted(rows, key=lambda item: item.metric_date)
    ]
    latest = points[-1] if points else None
    seven_start = today - timedelta(days=6)
    month_start = today - timedelta(days=27)
    previous_cutoff = today - timedelta(days=28)

    change = None
    change_pct = None
    if latest is not None:
        older = [point for point in points if point.date <= previous_cutoff]
        if older:
            reference = older[-1]
            change = round(latest.value - reference.value, 2)
            change_pct = round(change / max(abs(reference.value), 1e-9) * 100.0, 1)

    return RecoveryMetricOut(
        key=key,
        unit=METRIC_UNITS[key],
        latest_value=latest.value if latest else None,
        latest_date=latest.date if latest else None,
        avg_7d=_average([point.value for point in points if point.date >= seven_start]),
        avg_28d=_average([point.value for point in points if point.date >= month_start]),
        change_28d=change,
        change_28d_pct=change_pct,
        samples=len(points),
        coverage_days=len({point.date for point in points}),
        points=points,
    )


def build_recovery(
    db: Session,
    days: int = DEFAULT_DAYS,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> RecoveryOverview:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()
    days = max(7, min(days, 730))
    start = today - timedelta(days=days - 1)

    rows = db.scalars(
        select(ExternalMetric)
        .where(
            ExternalMetric.source == GARMIN_SOURCE,
            ExternalMetric.metric.in_(list(METRIC_UNITS)),
            ExternalMetric.metric_date >= start,
            ExternalMetric.metric_date <= today,
        )
        .order_by(ExternalMetric.metric_date)
    ).all()
    by_metric: dict[str, list[ExternalMetric]] = {key: [] for key in METRIC_UNITS}
    for row in rows:
        by_metric.setdefault(row.metric, []).append(row)

    metrics = [_metric(key, by_metric.get(key, []), today) for key in METRIC_UNITS]
    by_key = {metric.key: metric for metric in metrics}
    available_core = [key for key in CORE_METRICS if by_key[key].latest_value is not None]

    warnings: list[str] = []
    for key in METRIC_UNITS:
        if by_key[key].latest_value is None:
            warnings.append(METRIC_WARNINGS[key])
    if not available_core:
        warnings.append("no_recovery_data")
    elif len(available_core) < len(CORE_METRICS):
        warnings.append("partial_recovery_data")
    latest_dates = [metric.latest_date for metric in metrics if metric.latest_date is not None]
    if latest_dates and max(latest_dates) < today - timedelta(days=14):
        warnings.append("stale_recovery_data")
    if any(0 < metric.samples < 4 for metric in metrics):
        warnings.append("short_recovery_history")

    imported_at = max((row.imported_at for row in rows), default=None)
    status = "insufficient" if not available_core else "ok"
    if available_core and len(available_core) < len(CORE_METRICS):
        status = "partial"

    notes = [
        "recovery_is_context_only",
        "not_medical_advice",
        "from_garmin_export",
        "sleep_duration_in_seconds",
        "weight_is_not_a_performance_metric",
    ]
    if imported_at is None:
        notes.append("import_garmin_export")

    return RecoveryOverview(
        generated_at=reference,
        model_version=MODEL_VERSION,
        days=days,
        status=status,
        imported_at=imported_at,
        metrics=metrics,
        warnings=warnings,
        notes=notes,
    )
