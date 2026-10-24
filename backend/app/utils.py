"""Small shared helpers: time, hashing, sport normalisation."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, date, datetime, timedelta

RUNNING_SPORTS = {
    "running",
    "trail_running",
    "treadmill_running",
    "track_running",
    "indoor_running",
    "virtual_run",
    "obstacle_run",
    "ultra_running",
}

SPORT_ALIASES = {
    "run": "running",
    "running": "running",
    "trail": "trail_running",
    "trail_running": "trail_running",
    "trailrun": "trail_running",
    "treadmill": "treadmill_running",
    "treadmill_running": "treadmill_running",
    "indoor_running": "indoor_running",
    "track_running": "track_running",
    "virtual_run": "virtual_run",
    "cycling": "cycling",
    "biking": "cycling",
    "bike": "cycling",
    "walking": "walking",
    "hiking": "hiking",
    "swimming": "swimming",
    "strength_training": "strength_training",
    "strength": "strength_training",
    "other": "other",
}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_naive_utc(value: datetime) -> datetime:
    return as_utc(value).replace(tzinfo=None)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return as_utc(value)


def parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse the several datetime shapes returned by Garmin/FIT/TCX."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_naive_utc(value)
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
    ):
        try:
            return to_naive_utc(datetime.strptime(raw, fmt))
        except ValueError:
            pass
    try:
        return to_naive_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def parse_iso_datetime(value: str | datetime | None) -> datetime | None:
    return parse_datetime(value)


def local_date(value: datetime, offset_minutes: int) -> date:
    """Local calendar date for a naive-UTC datetime."""
    return (as_utc(value) + timedelta(minutes=offset_minutes)).date()


def local_datetime(value: datetime, offset_minutes: int) -> datetime:
    return (as_utc(value) + timedelta(minutes=offset_minutes)).replace(tzinfo=None)


def fingerprint(sport: str, start_time: datetime, distance_m: float | None) -> str:
    """Stable cross-source identity.

    A run cannot plausibly start in the same minute, with the same sport and the
    same 100 m distance bucket, twice. Manual uploads and Garmin sync therefore
    converge on the same row.
    """
    bucket = int(round((distance_m or 0) / 100.0))
    key = f"{normalize_sport(sport)}|{to_naive_utc(start_time):%Y-%m-%dT%H:%M}|{bucket}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_sport(value: str | None) -> str:
    if not value:
        return "other"
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    return SPORT_ALIASES.get(key, key)


def is_running(sport: str | None) -> bool:
    return normalize_sport(sport) in RUNNING_SPORTS


def safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.lower()).strip()
    return re.sub(r"[-\s]+", "-", value) or "activity"
