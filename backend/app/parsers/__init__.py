"""File format detection and parser dispatch."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from app.parsers.base import PARSER_VERSION, ParsedActivity, ParseError
from app.parsers.fit import parse_fit
from app.parsers.gpx import parse_gpx
from app.parsers.tcx import parse_tcx
from app.parsers.xml_utils import local_name

__all__ = [
    "PARSER_VERSION",
    "ParseError",
    "ParsedActivity",
    "detect_format",
    "parse_activity_file",
]


def detect_format(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n")

    if len(data) >= 12 and data[8:12] == b".FIT":
        return "fit"
    if head.startswith(b"PK\x03\x04"):
        raise ParseError("ZIP files are not supported directly; upload the FIT file inside")
    if head.startswith(b"<"):
        try:
            root = ET.fromstring(data)
            root_name = local_name(root.tag)
            if root_name == "TrainingCenterDatabase":
                return "tcx"
            if root_name == "gpx":
                return "gpx"
        except ET.ParseError:
            pass

    if suffix in {"fit", "tcx", "gpx"}:
        return suffix
    raise ParseError("Unsupported file format; expected FIT, TCX or GPX")


def parse_activity_file(filename: str, data: bytes) -> ParsedActivity:
    fmt = detect_format(filename, data)
    if fmt == "fit":
        activity = parse_fit(data)
    elif fmt == "tcx":
        activity = parse_tcx(data)
    elif fmt == "gpx":
        activity = parse_gpx(data)
    else:  # pragma: no cover - guarded by detect_format
        raise ParseError(f"Unsupported format: {fmt}")

    if activity.sport == "other":
        inferred = _infer_sport_from_filename(filename)
        if inferred:
            activity.sport = inferred
            activity.warnings.append("sport_inferred")

    return activity


def _infer_sport_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem.lower()
    if re.search(r"\b(trail|cross)\b", stem):
        return "trail_running"
    if re.search(r"\b(run|carrera|trote|5k|10k|21k|42k)\b", stem):
        return "running"
    if re.search(r"\b(ride|bici|bike|cycling)\b", stem):
        return "cycling"
    if re.search(r"\b(walk|paseo)\b", stem):
        return "walking"
    if re.search(r"\b(hike|senderismo)\b", stem):
        return "hiking"
    return None
