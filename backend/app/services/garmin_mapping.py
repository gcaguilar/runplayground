"""Translate Garmin activity JSON into the parser-neutral activity shape."""

from __future__ import annotations

from typing import Any

from app.parsers.base import ParsedActivity, ParseError
from app.utils import (
    RUNNING_SPORTS,
    normalize_sport,
    parse_datetime,
    safe_float,
    safe_int,
)


def _merged_summary(summary: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(summary)
    if detail:
        merged.update(detail.get("summaryDTO") or {})
    return merged


def parsed_from_garmin(
    summary: dict[str, Any], detail: dict[str, Any] | None = None
) -> ParsedActivity:
    """Build an activity from the list response, optionally enriched by detail."""
    if not summary:
        raise ParseError("Garmin returned an empty activity")

    data = _merged_summary(summary, detail)
    detail = detail or {}

    activity_type = detail.get("activityTypeDTO") or summary.get("activityType") or {}
    type_key = str(activity_type.get("typeKey") or "other")
    sport = normalize_sport(type_key)
    sub_sport = None
    if sport in RUNNING_SPORTS:
        sub_sport = None if sport == "running" else sport
        sport = "running"

    start = parse_datetime(data.get("startTimeGMT") or summary.get("startTimeGMT"))
    if start is None:
        raise ParseError("Garmin activity has no start time")

    distance = safe_float(data.get("distance")) or 0.0
    duration = safe_float(data.get("duration")) or 0.0
    if duration <= 0:
        duration = safe_float(data.get("elapsedDuration")) or 0.0
    if distance <= 0 and duration <= 0:
        raise ParseError("Garmin activity has no distance or duration")

    cadence = (
        safe_float(data.get("averageRunCadence"))
        or safe_float(data.get("averageRunningCadenceInStepsPerMinute"))
        or safe_float(data.get("averageBikeCadence"))
        or safe_float(data.get("averageBikingCadenceInRevPerMinute"))
    )
    max_cadence = (
        safe_float(data.get("maxRunCadence"))
        or safe_float(data.get("maxRunningCadenceInStepsPerMinute"))
        or safe_float(data.get("maxBikeCadence"))
        or safe_float(data.get("maxBikingCadenceInRevPerMinute"))
    )

    name = data.get("activityName") or summary.get("activityName")
    description = data.get("description") or summary.get("description")
    meta = detail.get("metadataDTO") or {}
    manufacturer = meta.get("manufacturer") or data.get("manufacturer")

    return ParsedActivity(
        sport=sport,
        sub_sport=sub_sport,
        start_time_utc=start,
        distance_m=distance,
        duration_s=duration,
        moving_s=safe_float(data.get("movingDuration")),
        elapsed_s=safe_float(data.get("elapsedDuration")),
        avg_hr=safe_int(data.get("averageHR")),
        max_hr=safe_int(data.get("maxHR")),
        avg_cadence_spm=cadence,
        max_cadence_spm=max_cadence,
        avg_speed_mps=safe_float(data.get("averageSpeed"))
        or safe_float(data.get("averageMovingSpeed")),
        max_speed_mps=safe_float(data.get("maxSpeed")),
        avg_power_w=safe_float(data.get("averagePower")) or safe_float(data.get("avgPower")),
        max_power_w=safe_float(data.get("maxPower")),
        elevation_gain_m=safe_float(data.get("elevationGain")),
        elevation_loss_m=safe_float(data.get("elevationLoss")),
        calories=safe_float(data.get("calories")),
        training_effect=safe_float(data.get("trainingEffect"))
        or safe_float(data.get("aerobicTrainingEffect")),
        training_load=safe_float(data.get("activityTrainingLoad")),
        name=str(name) if name else None,
        description=str(description) if description else None,
        manufacturer=str(manufacturer) if manufacturer else None,
    )


def merge_fit_with_garmin(fit: ParsedActivity, garmin: ParsedActivity) -> ParsedActivity:
    """Keep FIT streams/laps but prefer Garmin's canonical totals and naming."""
    fit.name = garmin.name or fit.name
    fit.description = garmin.description or fit.description
    fit.manufacturer = fit.manufacturer or garmin.manufacturer
    fit.training_effect = garmin.training_effect or fit.training_effect
    fit.training_load = garmin.training_load or fit.training_load

    for field in (
        "distance_m",
        "duration_s",
        "moving_s",
        "elapsed_s",
        "avg_hr",
        "max_hr",
        "avg_cadence_spm",
        "max_cadence_spm",
        "avg_speed_mps",
        "max_speed_mps",
        "avg_power_w",
        "max_power_w",
        "elevation_gain_m",
        "elevation_loss_m",
        "calories",
    ):
        garmin_value = getattr(garmin, field, None)
        if garmin_value not in (None, 0, 0.0):
            setattr(fit, field, garmin_value)

    fit.warnings = list(dict.fromkeys([*fit.warnings, *garmin.warnings]))
    return fit
