"""GPX parser (tracks only; routes and waypoints are ignored)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.parsers.base import ParsedActivity, ParsedSample, ParseError
from app.parsers.common import finalize_with_warnings
from app.parsers.xml_utils import child_text, children, local_name
from app.utils import haversine_m, normalize_sport, parse_datetime, safe_float, safe_int


def _gpx_extension(point: ET.Element, names: set[str]) -> float | None:
    for item in point.iter():
        if local_name(item.tag) in names and item.text:
            return safe_float(item.text)
    return None


def parse_gpx(data: bytes) -> ParsedActivity:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"Invalid GPX XML: {exc}") from exc

    track = next((item for item in root.iter() if local_name(item.tag) == "trk"), None)
    if track is None:
        raise ParseError("GPX file has no track")

    name = child_text(track, "name")
    sport = normalize_sport(child_text(track, "type") or "other")

    samples: list[ParsedSample] = []
    cumulative = 0.0
    previous: tuple[float, float] | None = None

    for segment in children(track, "trkseg"):
        previous = None
        for point in children(segment, "trkpt"):
            lat = safe_float(point.attrib.get("lat"))
            lon = safe_float(point.attrib.get("lon"))
            if lat is not None and lon is not None and previous is not None:
                cumulative += haversine_m(previous[0], previous[1], lat, lon)
            if lat is not None and lon is not None:
                previous = (lat, lon)

            elevation = safe_float(child_text(point, "ele"))
            hr = _gpx_extension(point, {"hr", "heartrate", "HeartRate"})
            cadence = _gpx_extension(point, {"cad", "cadence", "Cadence"})
            speed = _gpx_extension(point, {"speed", "Speed"})

            samples.append(
                ParsedSample(
                    timestamp_utc=parse_datetime(child_text(point, "time")),
                    distance_m=cumulative,
                    heart_rate=safe_int(hr),
                    cadence_spm=cadence,
                    speed_mps=speed,
                    elevation_m=elevation,
                    latitude=lat,
                    longitude=lon,
                )
            )

    timestamps = [sample.timestamp_utc for sample in samples if sample.timestamp_utc is not None]
    if not timestamps:
        raise ParseError("GPX track has no timestamps")
    start = min(timestamps)
    duration = (max(timestamps) - start).total_seconds()

    activity = ParsedActivity(
        sport=sport,
        start_time_utc=start,
        distance_m=cumulative,
        duration_s=duration,
        moving_s=duration,
        elapsed_s=duration,
        name=name,
        samples=samples,
    )
    if sport == "other":
        activity.warnings.append("sport_unknown")

    return finalize_with_warnings(activity)
