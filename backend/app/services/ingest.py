"""Persist parsed activities with provenance and cross-source deduplication."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Activity, ActivityLap, ActivitySource, RawFile, StreamSample
from app.parsers import PARSER_VERSION, ParsedActivity, ParseError, parse_activity_file
from app.utils import fingerprint, sha256_bytes

logger = logging.getLogger(__name__)


@dataclass
class IngestOutcome:
    filename: str
    status: str
    activity_id: int | None = None
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


def store_raw_file(
    db: Session,
    data: bytes,
    filename: str,
    content_type: str,
    source: str,
) -> RawFile:
    settings = get_settings()
    digest = sha256_bytes(data)
    existing = db.scalar(select(RawFile).where(RawFile.sha256 == digest))
    if existing:
        return existing

    extension = Path(filename).suffix.lower()
    if extension not in {".fit", ".tcx", ".gpx"}:
        extension = ".fit" if len(data) >= 12 and data[8:12] == b".FIT" else ".bin"
    relative = Path("raw") / digest[:2] / f"{digest}{extension}"
    absolute = settings.data_dir / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    if not absolute.exists():
        temporary = absolute.with_suffix(absolute.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(absolute)

    raw_file = RawFile(
        sha256=digest,
        filename=filename,
        content_type=content_type or _content_type_for(extension),
        size_bytes=len(data),
        storage_path=relative.as_posix(),
        source=source,
    )
    db.add(raw_file)
    db.flush()
    return raw_file


def ingest_upload(
    db: Session, filename: str, data: bytes, content_type: str | None = None
) -> IngestOutcome:
    try:
        parsed = parse_activity_file(filename, data)
    except ParseError as exc:
        return IngestOutcome(filename=filename, status="error", message=str(exc))
    except Exception as exc:  # pragma: no cover - defensive around third-party decoders
        logger.exception("Unexpected parser failure for %s", filename)
        return IngestOutcome(
            filename=filename,
            status="error",
            message=f"Could not parse file: {exc}",
        )

    return upsert_parsed(
        db,
        parsed,
        source="upload",
        external_id=sha256_bytes(data),
        filename=filename,
        content_type=content_type or _content_type_for(Path(filename).suffix.lower()),
        data=data,
    )


def ingest_garmin(
    db: Session,
    parsed: ParsedActivity,
    activity_id: int | str,
    fit_bytes: bytes | None = None,
    warning: str | None = None,
) -> IngestOutcome:
    warnings = list(parsed.warnings)
    if warning:
        warnings.append(warning)
    return upsert_parsed(
        db,
        parsed,
        source="garmin_api",
        external_id=str(activity_id),
        filename=f"garmin-{activity_id}.fit" if fit_bytes else f"garmin-{activity_id}.json",
        content_type="application/vnd.garmin.fit" if fit_bytes else "application/json",
        data=fit_bytes,
        extra_warnings=warnings,
        source_meta={"garmin_activity_id": str(activity_id)},
    )


def upsert_parsed(
    db: Session,
    parsed: ParsedActivity,
    *,
    source: str,
    external_id: str,
    filename: str,
    content_type: str,
    data: bytes | None = None,
    extra_warnings: list[str] | None = None,
    source_meta: dict | None = None,
) -> IngestOutcome:
    raw_file = store_raw_file(db, data, filename, content_type, source) if data else None
    payload_hash = sha256_bytes(data) if data else None
    fp = fingerprint(parsed.sport, parsed.start_time_utc, parsed.distance_m)

    existing_source = db.scalar(
        select(ActivitySource).where(
            ActivitySource.source == source,
            ActivitySource.external_id == external_id,
        )
    )
    if existing_source is not None:
        activity = db.get(Activity, existing_source.activity_id)
        if activity is None:
            db.delete(existing_source)
            db.flush()
        elif not activity.has_streams and parsed.samples:
            _merge_activity(activity, parsed, prefer_incoming_time=source == "garmin_api")
            _replace_streams(db, activity, parsed)
            activity.quality_flags = _quality_flags(parsed, extra_warnings)
            db.commit()
            return IngestOutcome(
                filename=filename,
                status="merged",
                activity_id=activity.id,
                message="Streams added to an existing activity",
                warnings=_warnings(parsed, extra_warnings),
            )
        else:
            _merge_activity(activity, parsed, prefer_incoming_time=False)
            db.commit()
            return IngestOutcome(
                filename=filename,
                status="duplicate",
                activity_id=activity.id,
                message="Already imported",
                warnings=_warnings(parsed, extra_warnings),
            )

    activity = db.scalar(select(Activity).where(Activity.fingerprint == fp))
    if activity is not None:
        _merge_activity(activity, parsed, prefer_incoming_time=source == "garmin_api")
        should_replace = parsed.samples and not activity.has_streams
        if should_replace:
            _replace_streams(db, activity, parsed)
        activity.quality_flags = _quality_flags(parsed, extra_warnings)
        db.add(
            ActivitySource(
                activity_id=activity.id,
                source=source,
                external_id=external_id,
                raw_file_id=raw_file.id if raw_file else None,
                original_filename=filename,
                payload_sha256=payload_hash,
                parser_version=PARSER_VERSION,
                meta=source_meta or {},
            )
        )
        db.commit()
        return IngestOutcome(
            filename=filename,
            status="merged",
            activity_id=activity.id,
            message="Merged into an existing activity",
            warnings=_warnings(parsed, extra_warnings),
        )

    activity = Activity(
        fingerprint=fp,
        name=parsed.name or "",
        description=parsed.description,
        sport=parsed.sport,
        sub_sport=parsed.sub_sport,
        start_time_utc=parsed.start_time_utc,
        distance_m=parsed.distance_m,
        duration_s=parsed.duration_s,
        moving_s=parsed.moving_s,
        elapsed_s=parsed.elapsed_s,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        avg_cadence_spm=parsed.avg_cadence_spm,
        max_cadence_spm=parsed.max_cadence_spm,
        avg_speed_mps=parsed.avg_speed_mps,
        max_speed_mps=parsed.max_speed_mps,
        avg_power_w=parsed.avg_power_w,
        max_power_w=parsed.max_power_w,
        elevation_gain_m=parsed.elevation_gain_m,
        elevation_loss_m=parsed.elevation_loss_m,
        calories=parsed.calories,
        training_effect=parsed.training_effect,
        training_load=parsed.training_load,
        device_name=parsed.device_name,
        manufacturer=parsed.manufacturer,
        has_streams=bool(parsed.samples),
        has_gps=has_gps(parsed),
        has_laps=bool(parsed.laps),
        quality_flags=_quality_flags(parsed, extra_warnings),
    )
    db.add(activity)
    db.flush()

    if parsed.samples:
        _replace_streams(db, activity, parsed)

    db.add(
        ActivitySource(
            activity_id=activity.id,
            source=source,
            external_id=external_id,
            raw_file_id=raw_file.id if raw_file else None,
            original_filename=filename,
            payload_sha256=payload_hash,
            parser_version=PARSER_VERSION,
            meta=source_meta or {},
        )
    )
    db.commit()

    return IngestOutcome(
        filename=filename,
        status="imported",
        activity_id=activity.id,
        warnings=_warnings(parsed, extra_warnings),
    )


def has_gps(parsed: ParsedActivity) -> bool:
    return (
        sum(
            1
            for sample in parsed.samples
            if sample.latitude is not None and sample.longitude is not None
        )
        >= 2
    )


def _merge_activity(
    activity: Activity,
    parsed: ParsedActivity,
    *,
    prefer_incoming_time: bool,
) -> None:
    if prefer_incoming_time:
        activity.start_time_utc = parsed.start_time_utc
    if not activity.name and parsed.name:
        activity.name = parsed.name
    if not activity.description and parsed.description:
        activity.description = parsed.description
    if activity.sport == "other" and parsed.sport != "other":
        activity.sport = parsed.sport
    if not activity.sub_sport and parsed.sub_sport:
        activity.sub_sport = parsed.sub_sport

    scalar_fields = (
        "distance_m",
        "duration_s",
        "moving_s",
        "elapsed_s",
        "avg_hr",
        "max_hr",
        "avg_cadence_spm",
        "max_cadence_spm",
        "avg_speed_mps",
        "max_speed_mps",
        "avg_power_w",
        "max_power_w",
        "elevation_gain_m",
        "elevation_loss_m",
        "calories",
        "training_effect",
        "training_load",
    )
    for attribute in scalar_fields:
        current = getattr(activity, attribute)
        incoming = getattr(parsed, attribute)
        if incoming not in (None, 0, 0.0) and current in (None, 0, 0.0):
            setattr(activity, attribute, incoming)

    if not activity.device_name and parsed.device_name:
        activity.device_name = parsed.device_name
    if not activity.manufacturer and parsed.manufacturer:
        activity.manufacturer = parsed.manufacturer


def _replace_streams(db: Session, activity: Activity, parsed: ParsedActivity) -> None:
    db.execute(delete(StreamSample).where(StreamSample.activity_id == activity.id))
    db.execute(delete(ActivityLap).where(ActivityLap.activity_id == activity.id))

    first_timestamp: datetime | None = next(
        (sample.timestamp_utc for sample in parsed.samples if sample.timestamp_utc is not None),
        None,
    )
    rows = []
    for index, sample in enumerate(parsed.samples):
        elapsed = sample.elapsed_s
        if elapsed is None and sample.timestamp_utc is not None and first_timestamp is not None:
            elapsed = (sample.timestamp_utc - first_timestamp).total_seconds()
        rows.append(
            {
                "activity_id": activity.id,
                "sample_index": index,
                "timestamp_utc": sample.timestamp_utc,
                "elapsed_s": elapsed,
                "distance_m": sample.distance_m,
                "heart_rate": sample.heart_rate,
                "cadence_spm": sample.cadence_spm,
                "speed_mps": sample.speed_mps,
                "elevation_m": sample.elevation_m,
                "latitude": sample.latitude,
                "longitude": sample.longitude,
                "power_w": sample.power_w,
                "temperature_c": sample.temperature_c,
            }
        )
    for offset in range(0, len(rows), 500):
        db.execute(insert(StreamSample), rows[offset : offset + 500])

    for lap in parsed.laps:
        db.add(
            ActivityLap(
                activity_id=activity.id,
                lap_index=lap.lap_index,
                start_time_utc=lap.start_time_utc,
                distance_m=lap.distance_m,
                timer_s=lap.timer_s,
                elapsed_s=lap.elapsed_s,
                avg_hr=lap.avg_hr,
                max_hr=lap.max_hr,
                avg_cadence_spm=lap.avg_cadence_spm,
                max_cadence_spm=lap.max_cadence_spm,
                avg_speed_mps=lap.avg_speed_mps,
                max_speed_mps=lap.max_speed_mps,
                ascent_m=lap.ascent_m,
                descent_m=lap.descent_m,
                calories=lap.calories,
            )
        )

    activity.has_streams = bool(parsed.samples)
    activity.has_gps = has_gps(parsed)
    activity.has_laps = bool(parsed.laps)
    db.flush()


def _quality_flags(parsed: ParsedActivity, extra: list[str] | None) -> dict:
    flags = set(parsed.warnings)
    if extra:
        flags.update(extra)
    if not parsed.samples:
        flags.add("no_streams")
    if not has_gps(parsed):
        flags.add("no_gps")
    if parsed.avg_hr is None:
        flags.add("no_hr")
    if not parsed.laps:
        flags.add("no_laps")
    if parsed.distance_m <= 0:
        flags.add("zero_distance")
    if parsed.duration_s <= 0:
        flags.add("zero_duration")
    return {"flags": sorted(flags), "parser_version": PARSER_VERSION}


def _warnings(parsed: ParsedActivity, extra: list[str] | None) -> list[str]:
    return sorted(set([*parsed.warnings, *(extra or [])]))


def _content_type_for(extension: str) -> str:
    return {
        ".fit": "application/vnd.garmin.fit",
        ".tcx": "application/vnd.garmin.tcx+xml",
        ".gpx": "application/gpx+xml",
    }.get(extension.lower(), "application/octet-stream")
