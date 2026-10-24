"""Fastest continuous segment at a target distance.

The parser stores elapsed time and cumulative distance. This module turns those
streams into race-distance efforts without assuming a constant sample rate.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class SegmentEffort:
    distance_m: float
    duration_s: float
    start_s: float
    end_s: float
    method: str = "stream"


def build_points(
    times: list[float | None],
    distances: list[float | None],
) -> list[tuple[float, float]]:
    """Return clean ``(elapsed_s, distance_m)`` pairs with both monotonic."""

    points: list[tuple[float, float]] = []
    for raw_time, raw_distance in zip(times, distances, strict=False):
        if raw_time is None or raw_distance is None:
            continue
        if not math.isfinite(raw_time) or not math.isfinite(raw_distance):
            continue
        if raw_time < 0 or raw_distance < 0:
            continue
        if points:
            last_time, last_distance = points[-1]
            if raw_time < last_time:
                continue
            if raw_time == last_time:
                if raw_distance > last_distance:
                    points[-1] = (raw_time, raw_distance)
                continue
            if raw_distance < last_distance:
                # GPS noise can shave a few metres; a real reset would be a
                # different activity and is not useful for a continuous effort.
                if last_distance - raw_distance > 200:
                    continue
                raw_distance = last_distance
        points.append((raw_time, raw_distance))

    if not points:
        return []

    origin = points[0][1]
    if origin > 0:
        points = [(time, distance - origin) for time, distance in points]
    return points


def best_segment(
    points: list[tuple[float, float]],
    target_distance_m: float,
) -> SegmentEffort | None:
    if target_distance_m <= 0 or len(points) < 3:
        return None
    times = [point[0] for point in points]
    distances = [point[1] for point in points]
    total_distance = distances[-1]
    if total_distance < target_distance_m:
        return None

    best_time: float | None = None
    best_start = 0.0
    best_end = 0.0

    for index in range(len(points)):
        if best_time is not None and times[index] >= best_end:
            break
        target = distances[index] + target_distance_m
        if target > total_distance + 1e-6:
            break
        end_index = bisect_left(distances, target, lo=index + 1)
        if end_index >= len(points):
            break
        previous_index = end_index - 1
        span = distances[end_index] - distances[previous_index]
        if span <= 0:
            continue
        fraction = (target - distances[previous_index]) / span
        end_time = times[previous_index] + fraction * (times[end_index] - times[previous_index])
        duration = end_time - times[index]
        if duration <= 0:
            continue
        if best_time is None or duration < best_time - 0.01:
            best_time = duration
            best_start = times[index]
            best_end = end_time

    if best_time is None:
        return None
    return SegmentEffort(
        distance_m=target_distance_m,
        duration_s=round(best_time, 2),
        start_s=round(best_start, 2),
        end_s=round(best_end, 2),
    )


def stream_quality(
    points: list[tuple[float, float]],
    *,
    has_gps: bool,
    has_hr: bool,
    is_full_activity: bool,
) -> float:
    if len(points) < 3:
        return 0.35
    gaps = [
        points[index][0] - points[index - 1][0]
        for index in range(1, len(points))
        if points[index][0] > points[index - 1][0]
    ]
    spacing = median(gaps) if gaps else 10.0
    quality = 0.70
    if spacing <= 1.5:
        quality += 0.10
    elif spacing <= 3.0:
        quality += 0.06
    elif spacing <= 8.0:
        quality += 0.02
    else:
        quality -= 0.08
    if has_gps:
        quality += 0.07
    if has_hr:
        quality += 0.04
    if is_full_activity:
        quality += 0.04
    return round(max(0.35, min(0.97, quality)), 2)
