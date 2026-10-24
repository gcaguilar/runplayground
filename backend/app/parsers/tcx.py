"""TCX (Training Center XML) parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.parsers.base import ParsedActivity, ParsedLap, ParsedSample, ParseError
from app.parsers.common import finalize_with_warnings
from app.parsers.xml_utils import child, child_text, children, local_name
from app.utils import normalize_sport, parse_datetime, safe_float, safe_int


def _hr(element: ET.Element, name: str) -> int | None:
    container = child(element, name)
    if container is None:
        return None
    return safe_int(child_text(container, "Value"))


def _position(element: ET.Element) -> tuple[float | None, float | None]:
    position = child(element, "Position")
    if position is None:
        return None, None
    return (
        safe_float(child_text(position, "LatitudeDegrees")),
        safe_float(child_text(position, "LongitudeDegrees")),
    )


def _extension_speed(point: ET.Element) -> float | None:
    for item in point.iter():
        if local_name(item.tag) in {"Speed", "speed"} and item.text:
            return safe_float(item.text)
    return None


def _extension_cadence(point: ET.Element) -> float | None:
    for item in point.iter():
        if local_name(item.tag) in {"RunCadence", "Cadence", "cadence"} and item.text:
            return safe_float(item.text)
    return None


def parse_tcx(data: bytes) -> ParsedActivity:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"Invalid TCX XML: {exc}") from exc

    activity_element = None
    for element in root.iter():
        if local_name(element.tag) == "Activity":
            activity_element = element
            break
    if activity_element is None:
        raise ParseError("TCX file has no Activity element")

    sport = normalize_sport(activity_element.attrib.get("Sport", "other"))
    start = parse_datetime(child_text(activity_element, "Id"))

    samples: list[ParsedSample] = []
    laps: list[ParsedLap] = []

    for lap_element in children(activity_element, "Lap"):
        start = start or parse_datetime(lap_element.attrib.get("StartTime"))
        lap = ParsedLap(
            lap_index=len(laps),
            start_time_utc=parse_datetime(lap_element.attrib.get("StartTime")),
            distance_m=safe_float(child_text(lap_element, "DistanceMeters")),
            timer_s=safe_float(child_text(lap_element, "TotalTimeSeconds")),
            elapsed_s=safe_float(child_text(lap_element, "TotalTimeSeconds")),
            avg_hr=_hr(lap_element, "AverageHeartRateBpm"),
            max_hr=_hr(lap_element, "MaximumHeartRateBpm"),
            avg_cadence_spm=safe_float(child_text(lap_element, "Cadence")),
            max_speed_mps=safe_float(child_text(lap_element, "MaximumSpeed")),
            calories=safe_float(child_text(lap_element, "Calories")),
        )
        laps.append(lap)

        for track in children(lap_element, "Track"):
            for point in children(track, "Trackpoint"):
                timestamp = parse_datetime(child_text(point, "Time"))
                lat, lon = _position(point)
                cadence = safe_float(child_text(point, "Cadence"))
                if cadence is None:
                    cadence = _extension_cadence(point)
                samples.append(
                    ParsedSample(
                        timestamp_utc=timestamp,
                        distance_m=safe_float(child_text(point, "DistanceMeters")),
                        heart_rate=_hr(point, "HeartRateBpm"),
                        cadence_spm=cadence,
                        speed_mps=_extension_speed(point),
                        elevation_m=safe_float(child_text(point, "AltitudeMeters")),
                        latitude=lat,
                        longitude=lon,
                    )
                )

    if start is None:
        start = next(
            (sample.timestamp_utc for sample in samples if sample.timestamp_utc is not None), None
        )
    if start is None:
        raise ParseError("TCX file has no start time")

    duration = sum(lap.timer_s or 0.0 for lap in laps)
    distance = sum(lap.distance_m or 0.0 for lap in laps)
    if distance <= 0 and samples:
        distance = max((sample.distance_m or 0.0 for sample in samples), default=0.0)

    avg_hr_value = _weighted_average([(lap.avg_hr, lap.timer_s) for lap in laps])

    activity = ParsedActivity(
        sport=sport,
        start_time_utc=start,
        distance_m=distance,
        duration_s=duration,
        moving_s=duration,
        elapsed_s=duration,
        avg_hr=round(avg_hr_value) if avg_hr_value is not None else None,
        max_hr=max((lap.max_hr or 0 for lap in laps), default=0) or None,
        avg_cadence_spm=_weighted_average([(lap.avg_cadence_spm, lap.timer_s) for lap in laps]),
        max_speed_mps=max((lap.max_speed_mps or 0 for lap in laps), default=0) or None,
        samples=samples,
        laps=laps,
        warnings=[],
    )

    notes = child_text(activity_element, "Notes")
    if notes:
        activity.name = notes

    return finalize_with_warnings(activity)


def _weighted_average(values: list[tuple[float | int | None, float | None]]) -> float | None:
    total_weight = 0.0
    total = 0.0
    for value, weight in values:
        if value is None:
            continue
        effective_weight = weight or 1.0
        total += float(value) * effective_weight
        total_weight += effective_weight
    if total_weight <= 0:
        return None
    return total / total_weight
