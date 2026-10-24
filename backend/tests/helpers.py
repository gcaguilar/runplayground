from __future__ import annotations

from datetime import UTC, datetime, timedelta


def make_matching_tcx() -> bytes:
    """A TCX for the same session as sample.fit (same start, 5 km in 30 min)."""
    start = datetime(2026, 5, 30, 7, 0, tzinfo=UTC)
    laps = []
    for lap_index in range(5):
        points = []
        for point_index in range(13):
            seconds = lap_index * 360 + point_index * 30
            distance = lap_index * 1000 + point_index * (1000 / 12)
            timestamp = (start + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
            points.append(
                f"""<Trackpoint><Time>{timestamp}</Time><DistanceMeters>{distance:.1f}</DistanceMeters>
<HeartRateBpm><Value>{130 + lap_index * 7}</Value></HeartRateBpm><Cadence>84</Cadence>
<Extensions><TPX xmlns="http://www.garmin.com/xmlschemas/ActivityExtension/v2"><Speed>2.778</Speed></TPX></Extensions></Trackpoint>"""
            )
        lap_start = (start + timedelta(seconds=lap_index * 360)).strftime("%Y-%m-%dT%H:%M:%SZ")
        laps.append(
            f"""<Lap StartTime="{lap_start}">
<TotalTimeSeconds>360</TotalTimeSeconds><DistanceMeters>1000</DistanceMeters><Calories>80</Calories>
<AverageHeartRateBpm><Value>{130 + lap_index * 7}</Value></AverageHeartRateBpm>
<MaximumHeartRateBpm><Value>{140 + lap_index * 7}</Value></MaximumHeartRateBpm>
<Cadence>84</Cadence><Track>{"".join(points)}</Track></Lap>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities><Activity Sport="Running">
    <Id>{start.strftime("%Y-%m-%dT%H:%M:%SZ")}</Id>
    {"".join(laps)}
  </Activity></Activities>
</TrainingCenterDatabase>""".encode()
