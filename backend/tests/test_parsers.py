from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import ParseError, detect_format, parse_activity_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_fit_parser_reads_summary_streams_and_laps():
    data = (FIXTURES / "sample.fit").read_bytes()
    activity = parse_activity_file("sample.fit", data)

    assert activity.sport == "running"
    assert activity.start_time_utc.isoformat() == "2026-05-30T07:00:00"
    assert activity.distance_m == pytest.approx(5000, abs=1)
    assert activity.duration_s == pytest.approx(1800, abs=1)
    assert activity.avg_hr == 146
    assert activity.max_hr == 171
    assert activity.avg_cadence_spm == 168
    assert activity.elevation_gain_m == 15
    assert activity.device_name == "Forerunner 265"
    assert activity.manufacturer == "garmin"
    assert len(activity.samples) == 1801
    assert len(activity.laps) == 3
    assert activity.samples[0].latitude == pytest.approx(40.4168, abs=0.01)
    assert activity.laps[0].distance_m == pytest.approx(1666.67, abs=1)


def test_tcx_parser_reads_laps_and_trackpoints():
    data = (FIXTURES / "sample.tcx").read_bytes()
    activity = parse_activity_file("sample.tcx", data)

    assert activity.sport == "running"
    assert activity.distance_m == pytest.approx(3000, abs=1)
    assert activity.duration_s == pytest.approx(1080, abs=1)
    assert len(activity.laps) == 3
    assert len(activity.samples) == 39
    assert activity.avg_hr is not None and 130 < activity.avg_hr < 160
    assert activity.avg_cadence_spm == 168


def test_gpx_parser_reads_heart_rate_and_track():
    data = (FIXTURES / "sample.gpx").read_bytes()
    activity = parse_activity_file("sample.gpx", data)

    assert activity.sport == "running"
    assert activity.name == "GPX test run"
    assert len(activity.samples) == 37
    assert activity.avg_hr is not None
    assert activity.max_hr == 156
    assert activity.distance_m > 0
    assert activity.warnings == ["no_laps"]


def test_detect_format_uses_content_not_only_extension():
    fit = (FIXTURES / "sample.fit").read_bytes()
    assert detect_format("renamed.bin", fit) == "fit"
    gpx = (FIXTURES / "sample.gpx").read_bytes()
    assert detect_format("renamed.xml", gpx) == "gpx"


def test_unsupported_file_is_rejected():
    with pytest.raises(ParseError):
        parse_activity_file("notes.txt", b"hello world")
