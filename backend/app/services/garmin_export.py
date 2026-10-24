"""Garmin Connect data export (ZIP) parser.

Garmin's "Export your data" archive is a ZIP with JSON dumps under
``DI_CONNECT/...``. The exact shape changes between export versions, so the
parser is intentionally tolerant: it walks every JSON document, recognises a
small set of well-known metric fields, and ignores everything else. Original
FIT activities inside the archive are imported with the normal parser.
"""

from __future__ import annotations

import gzip
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExternalMetric
from app.services.ingest import IngestOutcome, ingest_upload
from app.utils import utcnow

GARMIN_SOURCE = "garmin_export"
MAX_ENTRY_BYTES = 80 * 1024 * 1024
MAX_TOTAL_JSON_BYTES = 600 * 1024 * 1024
MAX_FIT_FILES = 2000
MAX_FIT_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_FIT_BYTES = 1024 * 1024 * 1024

DISTANCE_KEYS: dict[str, float] = {
    "5k": 5000.0,
    "5km": 5000.0,
    "fivek": 5000.0,
    "time5k": 5000.0,
    "prediction5k": 5000.0,
    "10k": 10000.0,
    "10km": 10000.0,
    "tenk": 10000.0,
    "time10k": 10000.0,
    "prediction10k": 10000.0,
    "half": 21097.5,
    "hm": 21097.5,
    "halfmarathon": 21097.5,
    "halfmarathon_time": 21097.5,
    "timehalfmarathon": 21097.5,
    "predictionhalfmarathon": 21097.5,
    "marathon": 42195.0,
    "fullmarathon": 42195.0,
    "timemarathon": 42195.0,
    "predictionmarathon": 42195.0,
}

VO2MAX_KEYS = {
    "vo2max",
    "vo2maxvalue",
    "vo2maxprecisevalue",
    "genericvo2max",
    "runningvo2max",
    "vo2maxrunning",
    "cyclingvo2max",
    "vo2maxcycling",
}

READINESS_KEYS = {
    "trainingreadiness",
    "trainingreadinessscore",
    "readinessscore",
    "score",
}

LOAD_KEYS = {
    "acutetrainingload": "acute_training_load",
    "acuteload": "acute_training_load",
    "atl": "acute_training_load",
    "chronictrainingload": "chronic_training_load",
    "chronicload": "chronic_training_load",
    "ctl": "chronic_training_load",
}

DATE_KEYS = (
    "calendardate",
    "metricdate",
    "date",
    "timestamp",
    "starttimegmt",
    "starttime",
    "begintimestamp",
    "activitydate",
    "datetime",
)


@dataclass
class MetricSample:
    metric: str
    metric_date: date
    value: float
    unit: str = ""
    distance_m: float = 0.0
    source_file: str = ""
    source_key: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class GarminExportResult:
    files_scanned: int = 0
    metrics_imported: int = 0
    metrics_skipped: int = 0
    activities_imported: int = 0
    activities_merged: int = 0
    activities_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def import_garmin_export(
    db: Session,
    data: bytes,
    filename: str = "garmin-export.zip",
) -> GarminExportResult:
    result = GarminExportResult()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        result.warnings.append("invalid_zip")
        return result

    samples: dict[tuple[str, date, float], MetricSample] = {}
    total_json_bytes = 0
    total_fit_bytes = 0
    fit_count = 0

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            lowered = name.lower()
            is_json = lowered.endswith((".json", ".json.gz"))
            is_fit = lowered.endswith(".fit")
            if not (is_json or is_fit):
                continue
            result.files_scanned += 1
            if info.flag_bits & 0x1:
                result.warnings.append(f"encrypted_entry:{_short(name)}")
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                result.warnings.append(f"entry_too_large:{_short(name)}")
                continue

            if is_fit:
                if fit_count >= MAX_FIT_FILES:
                    result.warnings.append("fit_file_limit")
                    continue
                if info.file_size > MAX_FIT_FILE_BYTES:
                    result.warnings.append(f"fit_too_large:{_short(name)}")
                    continue
                total_fit_bytes += info.file_size
                if total_fit_bytes > MAX_TOTAL_FIT_BYTES:
                    result.warnings.append("fit_budget_exceeded")
                    break
                fit_count += 1
                try:
                    payload = archive.read(info)
                except (RuntimeError, zipfile.BadZipFile):
                    result.warnings.append(f"unreadable_entry:{_short(name)}")
                    continue
                outcome = ingest_upload(
                    db,
                    _basename(name),
                    payload,
                    "application/vnd.garmin.fit",
                    source=GARMIN_SOURCE,
                )
                _count_activity(result, outcome)
                continue

            total_json_bytes += info.file_size
            if total_json_bytes > MAX_TOTAL_JSON_BYTES:
                result.warnings.append("json_budget_exceeded")
                break
            try:
                payload = archive.read(info)
                if lowered.endswith(".gz"):
                    payload = gzip.decompress(payload)
                document = json.loads(payload)
            except (RuntimeError, zipfile.BadZipFile, OSError, json.JSONDecodeError):
                result.warnings.append(f"invalid_json:{_short(name)}")
                continue

            _collect_document(document, _basename(name), samples)

    if not samples and not result.activities_imported and not result.activities_merged:
        result.warnings.append("no_supported_data")

    for _key, sample in samples.items():
        existing = db.scalar(
            select(ExternalMetric).where(
                ExternalMetric.source == GARMIN_SOURCE,
                ExternalMetric.metric == sample.metric,
                ExternalMetric.metric_date == sample.metric_date,
                ExternalMetric.distance_m == sample.distance_m,
            )
        )
        if existing is not None and math.isclose(existing.value, sample.value, rel_tol=1e-9):
            result.metrics_skipped += 1
            continue
        if existing is None:
            existing = ExternalMetric(
                source=GARMIN_SOURCE,
                metric=sample.metric,
                metric_date=sample.metric_date,
                distance_m=sample.distance_m,
            )
            db.add(existing)
        existing.value = sample.value
        existing.unit = sample.unit
        existing.source_file = sample.source_file
        existing.source_key = sample.source_key
        existing.raw = sample.raw
        existing.imported_at = utcnow()
        result.metrics_imported += 1

    db.commit()
    return result


def _count_activity(result: GarminExportResult, outcome: IngestOutcome) -> None:
    if outcome.status == "imported":
        result.activities_imported += 1
    elif outcome.status == "merged":
        result.activities_merged += 1
    elif outcome.status == "duplicate":
        result.activities_skipped += 1
    else:
        result.warnings.append(f"activity_error:{_short(outcome.filename)}")


def _collect_document(
    document: Any,
    filename: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    hint = _normalise(filename.rsplit(".", 1)[0])
    _walk(document, filename, hint, samples)


def _walk(
    node: Any,
    filename: str,
    hint: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, filename, hint, samples)
        return
    if not isinstance(node, dict):
        return

    _extract_vo2max(node, filename, hint, samples)
    _extract_readiness(node, filename, hint, samples)
    _extract_load(node, filename, hint, samples)
    _extract_race_predictions(node, filename, hint, samples)

    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk(value, filename, hint, samples)


def _extract_vo2max(
    record: dict,
    filename: str,
    hint: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    if "vo2max" not in hint and not any(_normalise(key) in VO2MAX_KEYS for key in record):
        return
    for key, value in record.items():
        if _normalise(key) not in VO2MAX_KEYS:
            continue
        number = _as_float(value if not isinstance(value, dict) else _dict_value(value))
        if number is None or not 15 <= number <= 95:
            continue
        metric_date = _record_date(record)
        if metric_date is None:
            continue
        _store(
            samples,
            MetricSample(
                metric="vo2max",
                metric_date=metric_date,
                value=round(number, 2),
                unit="ml/kg/min",
                source_file=filename,
                source_key=key,
                raw=_raw_record(record),
            ),
        )


def _extract_readiness(
    record: dict,
    filename: str,
    hint: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    if "trainingreadiness" not in hint and not any(
        _normalise(key) in {"trainingreadiness", "trainingreadinessscore", "readinessscore"}
        for key in record
    ):
        return
    for key, value in record.items():
        if _normalise(key) not in READINESS_KEYS:
            continue
        number = _as_float(value if not isinstance(value, dict) else _dict_value(value))
        if number is None or not 1 <= number <= 100:
            continue
        metric_date = _record_date(record)
        if metric_date is None:
            continue
        _store(
            samples,
            MetricSample(
                metric="training_readiness",
                metric_date=metric_date,
                value=round(number, 1),
                unit="score",
                source_file=filename,
                source_key=key,
                raw=_raw_record(record),
            ),
        )
        return


def _extract_load(
    record: dict,
    filename: str,
    hint: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    if (
        "trainingload" not in hint
        and "trainingstatus" not in hint
        and not any(_normalise(key) in LOAD_KEYS for key in record)
    ):
        return
    metric_date = _record_date(record)
    if metric_date is None:
        return
    for key, value in record.items():
        metric = LOAD_KEYS.get(_normalise(key))
        if metric is None:
            continue
        number = _as_float(value if not isinstance(value, dict) else _dict_value(value))
        if number is None or not 0 <= number <= 5000:
            continue
        _store(
            samples,
            MetricSample(
                metric=metric,
                metric_date=metric_date,
                value=round(number, 1),
                unit="load",
                source_file=filename,
                source_key=key,
                raw=_raw_record(record),
            ),
        )


def _extract_race_predictions(
    record: dict,
    filename: str,
    hint: str,
    samples: dict[tuple[str, date, float], MetricSample],
) -> None:
    race_context = "raceprediction" in hint or any(
        "raceprediction" in _normalise(key) for key in record
    )
    if not race_context:
        return

    metric_date = _record_date(record)
    if metric_date is None:
        return

    generic_distance = _generic_distance_from_record(record)
    if generic_distance is not None:
        distance, distance_key = generic_distance
        seconds = _as_duration(
            _first_value(record, ("time", "timeseconds", "timeinseconds", "value"))
        )
        if seconds is not None and 300 <= seconds <= 24 * 3600:
            _store_race_prediction(
                samples, filename, metric_date, distance, seconds, record, distance_key
            )
        return

    for key, value in record.items():
        normalised = _normalise(key)
        if "raceprediction" in normalised and isinstance(value, dict):
            # Nested ``{"racePrediction": {"5K": 1200}}`` payload.
            for nested_key, nested_value in value.items():
                distance = _distance_for_key(nested_key)
                seconds = _as_duration(nested_value)
                if distance is not None and seconds is not None:
                    _store_race_prediction(
                        samples, filename, metric_date, distance, seconds, record, nested_key
                    )
            continue
        distance = _distance_for_key(key)
        if distance is None:
            continue
        seconds = _as_duration(value)
        if seconds is None:
            continue
        _store_race_prediction(samples, filename, metric_date, distance, seconds, record, key)


def _store_race_prediction(
    samples: dict[tuple[str, date, float], MetricSample],
    filename: str,
    metric_date: date,
    distance_m: float,
    seconds: float,
    record: dict,
    source_key: str,
) -> None:
    if not 300 <= seconds <= 24 * 3600:
        return
    _store(
        samples,
        MetricSample(
            metric="race_prediction",
            metric_date=metric_date,
            distance_m=distance_m,
            value=round(seconds, 1),
            unit="s",
            source_file=filename,
            source_key=source_key,
            raw=_raw_record(record),
        ),
    )


def _store(
    samples: dict[tuple[str, date, float], MetricSample],
    sample: MetricSample,
) -> None:
    samples[(sample.metric, sample.metric_date, sample.distance_m)] = sample


def _record_date(record: dict) -> date | None:
    for key, value in record.items():
        if _normalise(key) in DATE_KEYS:
            parsed = _as_date(value)
            if parsed is not None:
                return parsed
    for key, value in record.items():
        if "date" in _normalise(key) or "timestamp" in _normalise(key):
            parsed = _as_date(value)
            if parsed is not None:
                return parsed
    return None


def _generic_distance_from_record(record: dict) -> tuple[float, str] | None:
    for key, _value in record.items():
        distance = _distance_for_key(key)
        if distance is not None:
            return distance, key
    for key, value in record.items():
        normalised = _normalise(key)
        if normalised not in {
            "distance",
            "distancem",
            "distancemeters",
            "distanceinkm",
            "distancekm",
        }:
            continue
        number = _as_float(value)
        if number is None:
            continue
        if normalised in {"distancem", "distancemeters"} or number > 100:
            candidate = number
        else:
            candidate = number * 1000.0
        for standard in (5000.0, 10000.0, 21097.5, 42195.0):
            if abs(candidate - standard) / standard <= 0.025:
                return standard, key
    return None


def _distance_for_key(key: str) -> float | None:
    normalised = _normalise(key)
    if normalised in DISTANCE_KEYS:
        return DISTANCE_KEYS[normalised]
    match = re.fullmatch(r"(?:time|prediction|race)?(5|10|21|42)(?:k|km)?", normalised)
    if match:
        return {
            "5": 5000.0,
            "10": 10000.0,
            "21": 21097.5,
            "42": 42195.0,
        }[match.group(1)]
    if normalised.endswith("halfmarathon") or normalised.endswith("half"):
        return 21097.5
    if normalised.endswith("marathon") and "half" not in normalised:
        return 42195.0
    return None


def _dict_value(value: dict) -> Any:
    for key in ("value", "load", "score", "trainingLoad"):
        if key in value:
            return value[key]
    return None


def _first_value(record: dict, keys: tuple[str, ...]) -> Any:
    normalised_keys = {_normalise(key) for key in keys}
    for key, value in record.items():
        if _normalise(key) in normalised_keys:
            return value
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _as_duration(value: Any) -> float | None:
    if isinstance(value, dict):
        value = _first_value(value, ("time", "timeseconds", "timeinseconds", "value", "seconds"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if ":" not in text:
        return _as_float(text)
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 10_000_000_000:  # milliseconds
            number /= 1000.0
        if number < 100_000_000:
            return None
        try:
            return datetime.fromtimestamp(number, tz=UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        return _as_date(int(text))
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text[:10], pattern).date()
            except ValueError:
                continue
        return None
    return parsed.date()


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _short(name: str) -> str:
    return _basename(name)[:80]


def _raw_record(record: dict) -> dict:
    """Keep provenance useful without copying huge activity payloads."""
    output: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            output[key] = value
        if len(output) >= 12:
            break
    return output
