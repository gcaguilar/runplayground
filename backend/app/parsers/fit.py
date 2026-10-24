"""FIT decoder built on fitdecode (MIT).

The official Garmin FIT SDK ships under the FIT Protocol License, which is not
compatible with distributing this project as GPL-3.0. fitdecode is an
independent MIT-licensed decoder and covers every field we need.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import fitdecode

from app.parsers.base import ParsedActivity, ParsedLap, ParsedSample, ParseError
from app.parsers.common import finalize_with_warnings
from app.utils import normalize_sport, safe_float, safe_int


def _value(frame: fitdecode.FitDataMessage, *names: str, default: Any = None) -> Any:
    for name in names:
        value = frame.get_value(name, fallback=None)
        if value is not None:
            return value
    return default


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return None


def _semicircles(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    if abs(number) > 180:
        return number * 180.0 / (2**31)
    return number


def _lap_from_frame(frame: fitdecode.FitDataMessage, index: int) -> ParsedLap:
    return ParsedLap(
        lap_index=index,
        start_time_utc=_dt(_value(frame, "start_time")),
        distance_m=safe_float(_value(frame, "total_distance")),
        timer_s=safe_float(_value(frame, "total_timer_time")),
        elapsed_s=safe_float(_value(frame, "total_elapsed_time")),
        avg_hr=safe_int(_value(frame, "avg_heart_rate")),
        max_hr=safe_int(_value(frame, "max_heart_rate")),
        avg_cadence_spm=safe_float(_value(frame, "avg_cadence")),
        max_cadence_spm=safe_float(_value(frame, "max_cadence")),
        avg_speed_mps=safe_float(_value(frame, "avg_speed", "enhanced_avg_speed")),
        max_speed_mps=safe_float(_value(frame, "max_speed", "enhanced_max_speed")),
        ascent_m=safe_float(_value(frame, "total_ascent")),
        descent_m=safe_float(_value(frame, "total_descent")),
        calories=safe_float(_value(frame, "total_calories")),
    )


def parse_fit(data: bytes) -> ParsedActivity:
    from io import BytesIO

    try:
        # No unit processor: we want metres, m/s and raw semicircles, and we
        # normalise coordinates ourselves.
        reader = fitdecode.FitReader(BytesIO(data))
    except Exception as exc:  # pragma: no cover - defensive
        raise ParseError(f"Could not open FIT file: {exc}") from exc

    session: fitdecode.FitDataMessage | None = None
    file_id: fitdecode.FitDataMessage | None = None
    records: list[ParsedSample] = []
    laps: list[ParsedLap] = []
    device_name: str | None = None
    manufacturer: str | None = None

    try:
        with reader as fit:
            for frame in fit:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue

                if frame.name == "file_id" and file_id is None:
                    file_id = frame
                    manufacturer = _value(frame, "manufacturer")
                elif frame.name == "device_info":
                    product_name = _value(frame, "product_name")
                    if product_name and not device_name:
                        device_name = str(product_name)
                elif frame.name == "session" and session is None:
                    session = frame
                elif frame.name == "lap":
                    laps.append(_lap_from_frame(frame, len(laps)))
                elif frame.name == "record":
                    timestamp = _dt(_value(frame, "timestamp"))
                    sample = ParsedSample(
                        timestamp_utc=timestamp,
                        distance_m=safe_float(_value(frame, "distance")),
                        heart_rate=safe_int(_value(frame, "heart_rate")),
                        cadence_spm=safe_float(_value(frame, "cadence")),
                        speed_mps=safe_float(_value(frame, "enhanced_speed", "speed")),
                        elevation_m=safe_float(_value(frame, "enhanced_altitude", "altitude")),
                        latitude=_semicircles(_value(frame, "position_lat")),
                        longitude=_semicircles(_value(frame, "position_long")),
                        power_w=safe_float(_value(frame, "power")),
                        temperature_c=safe_float(_value(frame, "temperature")),
                    )
                    records.append(sample)
    except Exception as exc:
        raise ParseError(f"Invalid or truncated FIT file: {exc}") from exc

    if file_id is not None:
        file_type = _value(file_id, "type")
        if file_type and str(file_type) not in {"activity", "4"}:
            raise ParseError(f"FIT file is not an activity (type={file_type})")

    if session is None:
        raise ParseError("FIT file has no session message")

    start = _dt(_value(session, "start_time"))
    if start is None:
        start = _dt(_value(session, "timestamp"))
    if start is None:
        raise ParseError("FIT session has no start time")

    sport = normalize_sport(str(_value(session, "sport", default="other")))
    sub_sport_raw = _value(session, "sub_sport")
    sub_sport = str(sub_sport_raw) if sub_sport_raw and str(sub_sport_raw) != "generic" else None

    product = _value(file_id, "product", "garmin_product") if file_id is not None else None
    if device_name is None and product and str(product) not in {"0", "65534", "None"}:
        device_name = str(product)

    activity = ParsedActivity(
        sport=sport,
        sub_sport=sub_sport,
        start_time_utc=start,
        distance_m=safe_float(_value(session, "total_distance")) or 0.0,
        duration_s=safe_float(_value(session, "total_timer_time")) or 0.0,
        moving_s=safe_float(_value(session, "total_timer_time")),
        elapsed_s=safe_float(_value(session, "total_elapsed_time")),
        avg_hr=safe_int(_value(session, "avg_heart_rate")),
        max_hr=safe_int(_value(session, "max_heart_rate")),
        avg_cadence_spm=safe_float(_value(session, "avg_cadence")),
        max_cadence_spm=safe_float(_value(session, "max_cadence")),
        avg_speed_mps=safe_float(_value(session, "avg_speed", "enhanced_avg_speed")),
        max_speed_mps=safe_float(_value(session, "max_speed", "enhanced_max_speed")),
        avg_power_w=safe_float(_value(session, "avg_power")),
        max_power_w=safe_float(_value(session, "max_power")),
        elevation_gain_m=safe_float(_value(session, "total_ascent")),
        elevation_loss_m=safe_float(_value(session, "total_descent")),
        calories=safe_float(_value(session, "total_calories")),
        training_effect=safe_float(
            _value(session, "total_training_effect", "total_training_effect_v2")
        ),
        device_name=device_name,
        manufacturer=str(manufacturer) if manufacturer else None,
        samples=records,
        laps=laps,
    )

    return finalize_with_warnings(activity)
