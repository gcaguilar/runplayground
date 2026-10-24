"""Shared post-processing for FIT, TCX and GPX activities."""

from __future__ import annotations

from datetime import datetime
from statistics import median

from app.parsers.base import ParsedActivity, ParsedSample, ParseError
from app.utils import RUNNING_SPORTS, as_utc, is_running


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _fill_from_samples(activity: ParsedActivity) -> None:
    samples = activity.samples
    if not samples:
        return

    hrs = [float(s.heart_rate) for s in samples if s.heart_rate and s.heart_rate > 0]
    if activity.avg_hr is None and hrs:
        activity.avg_hr = round(_mean(hrs) or 0)
    if activity.max_hr is None and hrs:
        activity.max_hr = round(max(hrs))

    cadences = [s.cadence_spm for s in samples if s.cadence_spm and s.cadence_spm > 0]
    if activity.avg_cadence_spm is None and cadences:
        activity.avg_cadence_spm = round(_mean(cadences) or 0, 1)
    if activity.max_cadence_spm is None and cadences:
        activity.max_cadence_spm = round(max(cadences), 1)

    speeds = [s.speed_mps for s in samples if s.speed_mps and s.speed_mps > 0]
    if activity.avg_speed_mps is None and activity.distance_m and activity.duration_s:
        activity.avg_speed_mps = activity.distance_m / activity.duration_s
    if activity.max_speed_mps is None and speeds:
        activity.max_speed_mps = round(max(speeds), 3)

    powers = [s.power_w for s in samples if s.power_w and s.power_w > 0]
    if activity.avg_power_w is None and powers:
        activity.avg_power_w = round(_mean(powers) or 0, 1)
    if activity.max_power_w is None and powers:
        activity.max_power_w = round(max(powers), 1)

    if activity.elevation_gain_m is None or activity.elevation_loss_m is None:
        elevations = [s.elevation_m for s in samples if s.elevation_m is not None]
        if len(elevations) > 1:
            gain, loss = _elevation_totals(elevations)
            if activity.elevation_gain_m is None:
                activity.elevation_gain_m = gain
            if activity.elevation_loss_m is None:
                activity.elevation_loss_m = loss


def _elevation_totals(elevations: list[float]) -> tuple[float, float]:
    gain = 0.0
    loss = 0.0
    reference = elevations[0]
    threshold = 2.0
    for value in elevations[1:]:
        delta = value - reference
        if delta >= threshold:
            gain += delta
            reference = value
        elif delta <= -threshold:
            loss += -delta
            reference = value
    return round(gain, 1), round(loss, 1)


def _normalise_cadence(activity: ParsedActivity) -> None:
    """FIT/TCX running cadence is usually strides per minute.

    Garmin Connect displays steps per minute (roughly double). Some files
    already contain steps per minute, so only double running cadence when the
    activity average is in the plausible strides-per-minute band.
    """
    if not is_running(activity.sport):
        return

    values = [s.cadence_spm for s in activity.samples if s.cadence_spm and s.cadence_spm > 0]
    reference = activity.avg_cadence_spm or (median(values) if values else None)
    if not reference or reference > 120:
        return

    for sample in activity.samples:
        if sample.cadence_spm:
            sample.cadence_spm = round(sample.cadence_spm * 2, 1)
    if activity.avg_cadence_spm:
        activity.avg_cadence_spm = round(activity.avg_cadence_spm * 2, 1)
    if activity.max_cadence_spm:
        activity.max_cadence_spm = round(activity.max_cadence_spm * 2, 1)
    for lap in activity.laps:
        if lap.avg_cadence_spm:
            lap.avg_cadence_spm = round(lap.avg_cadence_spm * 2, 1)
        if lap.max_cadence_spm:
            lap.max_cadence_spm = round(lap.max_cadence_spm * 2, 1)


def _derive_timing(activity: ParsedActivity) -> None:
    samples = [s for s in activity.samples if s.timestamp_utc is not None]
    if samples:
        samples.sort(key=lambda s: as_utc(s.timestamp_utc))  # type: ignore[arg-type]
        first = as_utc(samples[0].timestamp_utc)  # type: ignore[arg-type]
        last = as_utc(samples[-1].timestamp_utc)  # type: ignore[arg-type]
        activity.start_time_utc = first.replace(tzinfo=None)
        span = (last - first).total_seconds()
        if activity.duration_s <= 0 and span > 0:
            activity.duration_s = span
        for sample in activity.samples:
            if sample.timestamp_utc is not None and sample.elapsed_s is None:
                sample.elapsed_s = round((as_utc(sample.timestamp_utc) - first).total_seconds(), 2)

    if activity.distance_m <= 0 and activity.samples:
        distances = [s.distance_m for s in activity.samples if s.distance_m is not None]
        if distances:
            activity.distance_m = max(distances)
    if activity.distance_m <= 0 and len(activity.samples) > 1:
        total = 0.0
        previous = None
        for sample in activity.samples:
            if sample.latitude is None or sample.longitude is None:
                continue
            if previous is not None:
                from app.utils import haversine_m

                total += haversine_m(previous[0], previous[1], sample.latitude, sample.longitude)
            previous = (sample.latitude, sample.longitude)
        activity.distance_m = total

    if activity.duration_s <= 0 and activity.samples:
        elapsed = [s.elapsed_s for s in activity.samples if s.elapsed_s is not None]
        if elapsed:
            activity.duration_s = max(elapsed)


def finalize(activity: ParsedActivity) -> ParsedActivity:
    if activity.start_time_utc is None:
        raise ParseError("The file does not contain a start time")

    activity.start_time_utc = as_utc(activity.start_time_utc).replace(tzinfo=None)
    activity.sport = activity.sport or "other"

    # All running variants share one canonical sport; the variant is preserved
    # as sub_sport so the UI can filter "trail" or "treadmill" later.
    if activity.sport in RUNNING_SPORTS and activity.sport != "running":
        activity.sub_sport = activity.sub_sport or activity.sport
        activity.sport = "running"

    # Keep only samples that carry at least one useful measurement.
    activity.samples = [
        sample
        for sample in activity.samples
        if any(
            value is not None
            for value in (
                sample.timestamp_utc,
                sample.distance_m,
                sample.heart_rate,
                sample.latitude,
                sample.longitude,
            )
        )
    ]

    _normalise_cadence(activity)
    _derive_timing(activity)
    _fill_from_samples(activity)

    if activity.distance_m < 0:
        activity.distance_m = 0.0
    if activity.duration_s < 0:
        activity.duration_s = 0.0
    if activity.distance_m <= 0 and activity.duration_s <= 0:
        raise ParseError("The file does not contain distance or duration data")

    if activity.avg_speed_mps is None and activity.duration_s > 0:
        activity.avg_speed_mps = activity.distance_m / activity.duration_s
    if activity.moving_s is None:
        activity.moving_s = activity.duration_s
    if activity.elapsed_s is None:
        activity.elapsed_s = activity.duration_s

    for lap in activity.laps:
        if lap.timer_s is None:
            lap.timer_s = lap.elapsed_s
        if lap.avg_speed_mps is None and lap.distance_m and lap.timer_s:
            lap.avg_speed_mps = lap.distance_m / lap.timer_s

    return activity


def finalize_with_warnings(activity: ParsedActivity) -> ParsedActivity:
    activity = finalize(activity)
    if not any(sample.latitude is not None for sample in activity.samples):
        activity.warnings.append("no_gps")
    if activity.avg_hr is None:
        activity.warnings.append("no_hr")
    if not activity.samples:
        activity.warnings.append("no_streams")
    if not activity.laps:
        activity.warnings.append("no_laps")
    return activity


def elapsed_from_samples(samples: list[ParsedSample]) -> float | None:
    stamps = [s.timestamp_utc for s in samples if s.timestamp_utc is not None]
    if len(stamps) < 2:
        return None
    return (as_utc(max(stamps)) - as_utc(min(stamps))).total_seconds()


def sum_distances(samples: list[ParsedSample]) -> float:
    distances = [s.distance_m for s in samples if s.distance_m is not None]
    return max(distances) if distances else 0.0


def first_timestamp(samples: list[ParsedSample]) -> datetime | None:
    stamps = [s.timestamp_utc for s in samples if s.timestamp_utc is not None]
    return min(stamps, key=as_utc) if stamps else None
