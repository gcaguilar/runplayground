"""Parser-neutral activity representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

PARSER_VERSION = "1"


class ParseError(ValueError):
    """Raised when a file cannot be decoded into an activity."""


@dataclass(slots=True)
class ParsedSample:
    timestamp_utc: datetime | None = None
    elapsed_s: float | None = None
    distance_m: float | None = None
    heart_rate: int | None = None
    cadence_spm: float | None = None
    speed_mps: float | None = None
    elevation_m: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    power_w: float | None = None
    temperature_c: float | None = None


@dataclass(slots=True)
class ParsedLap:
    lap_index: int
    start_time_utc: datetime | None = None
    distance_m: float | None = None
    timer_s: float | None = None
    elapsed_s: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence_spm: float | None = None
    max_cadence_spm: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    ascent_m: float | None = None
    descent_m: float | None = None
    calories: float | None = None


@dataclass(slots=True)
class ParsedActivity:
    sport: str
    start_time_utc: datetime
    distance_m: float
    duration_s: float
    name: str | None = None
    description: str | None = None
    sub_sport: str | None = None
    moving_s: float | None = None
    elapsed_s: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence_spm: float | None = None
    max_cadence_spm: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_power_w: float | None = None
    max_power_w: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    calories: float | None = None
    training_effect: float | None = None
    training_load: float | None = None
    device_name: str | None = None
    manufacturer: str | None = None
    samples: list[ParsedSample] = field(default_factory=list)
    laps: list[ParsedLap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
