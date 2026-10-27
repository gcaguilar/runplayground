"""Heart-rate zones for a single activity (M17).

The zones are context, not a diagnosis. They reuse the effective analysis
settings from M11 and prefer a manually configured threshold heart rate; when
there is no manual threshold they fall back to max HR, and only then to the
maximum observed in the activity or its stream. Every response states the
reference, the source and the method so the UI never presents an estimate as a
laboratory result.

Zone model
----------

Five zones with four internal cut points. The open ends absorb everything
inside the physiological range, so the zone times always add up to the time
with valid heart rate:

* max HR method: cuts at 60, 70, 80 and 90 % of max HR.
  Z1 <60 %, Z2 60-70 %, Z3 70-80 %, Z4 80-90 %, Z5 >=90 %.
* threshold HR method: cuts at 80, 90, 100 and 105 % of threshold HR.
  Z1 <80 %, Z2 80-90 %, Z3 90-100 %, Z4 100-105 %, Z5 >=105 %.

Cuts are rounded to whole bpm, clamped to the physiological window (30-230
bpm) and forced to be strictly increasing, so zones never overlap.

Time approximation
------------------

A stream sample covers the interval until the next sample (using ``elapsed_s``
or the timestamp difference). The last sample reuses the previous interval.
Intervals below zero are ignored; intervals longer than 60 s are treated as a
gap and are not assigned, which avoids counting a paused recording as time in
zone. Samples with heart rate outside 30-230 bpm are excluded. The endpoint
only reads the activity's own stream, so the cost is bounded by its sample
count and no whole-history scan is performed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, StreamSample
from app.schemas import HrZoneOut, HrZonesOut
from app.services.analysis_settings import ResolvedAnalysisSettings, get_analysis_settings

MODEL_VERSION = "m17.0"

MIN_VALID_HR = 30
MAX_VALID_HR = 230
MAX_SAMPLE_DELTA_S = 60.0
LOW_COVERAGE = 0.75
SPARSE_SAMPLES = 20

MAX_HR_CUT_PCTS: tuple[float, ...] = (60.0, 70.0, 80.0, 90.0)
THRESHOLD_HR_CUT_PCTS: tuple[float, ...] = (80.0, 90.0, 100.0, 105.0)

ZONE_KEYS: tuple[str, ...] = ("z1", "z2", "z3", "z4", "z5")


@dataclass
class ZoneBucket:
    key: str
    lower_bpm: int
    upper_bpm: int
    lower_pct: float | None
    upper_pct: float | None
    seconds: float = 0.0
    percentage: float = 0.0


@dataclass
class StreamTime:
    """One stream sample reduced to what the zone calculation needs."""

    elapsed_s: float | None
    timestamp_utc: datetime | None
    heart_rate: int | None


@dataclass
class ZoneResult:
    buckets: list[ZoneBucket] = field(default_factory=list)
    cuts_bpm: list[int] = field(default_factory=list)
    cuts_pct: list[float] = field(default_factory=list)
    samples_total: int = 0
    samples_timed: int = 0
    samples_with_hr: int = 0
    total_hr_s: float = 0.0
    avg_hr: int | None = None
    avg_hr_source: str | None = None
    max_hr: int | None = None
    max_hr_source: str | None = None
    stream_max_hr: int | None = None
    clipped_samples: int = 0
    gaps_skipped: int = 0


def build_activity_zones(db: Session, activity_id: int) -> HrZonesOut | None:
    """Return the zone breakdown for one activity, or ``None`` if missing."""

    activity = db.get(Activity, activity_id)
    if activity is None:
        return None

    rows = db.execute(
        select(
            StreamSample.elapsed_s,
            StreamSample.timestamp_utc,
            StreamSample.heart_rate,
        )
        .where(StreamSample.activity_id == activity_id)
        .order_by(StreamSample.sample_index)
    ).all()
    samples = [
        StreamTime(elapsed_s=row[0], timestamp_utc=row[1], heart_rate=row[2]) for row in rows
    ]

    settings = get_analysis_settings(db)
    stream_max = _stream_max(samples)
    method, source, reference_bpm = _resolve_reference(activity, settings, stream_max)
    warnings: list[str] = []
    notes: list[str] = []

    if not samples:
        warnings.append("no_streams")
    if stream_max is not None and source == "activity_fallback" and activity.max_hr is None:
        warnings.append("estimated_max_hr")
    if source == "activity_fallback":
        notes.append("activity_fallback_reference")
    if method == "threshold_hr":
        notes.append("threshold_reference")
    if activity.sport != "running":
        warnings.append("not_running")
    notes.append("time_weighted_by_sample_delta")

    if not samples:
        return _insufficient(
            activity,
            method=method,
            source=source,
            reference_bpm=reference_bpm,
            warnings=warnings,
            notes=notes,
            samples_total=0,
        )

    result = _calculate(samples, activity, method, reference_bpm)

    if method is None or reference_bpm is None:
        warnings.append("no_hr_reference")
    if result.samples_timed == 0:
        warnings.append("no_timed_samples")
    elif result.samples_with_hr == 0:
        warnings.append("no_hr")
    elif result.total_hr_s <= 0:
        warnings.append("no_hr_time")
    else:
        if result.clipped_samples:
            warnings.append("hr_filtered")
        if result.gaps_skipped:
            notes.append("stream_gaps_skipped")
        coverage = result.samples_with_hr / result.samples_timed
        if coverage < LOW_COVERAGE:
            warnings.append("low_coverage")
        if result.samples_with_hr < SPARSE_SAMPLES:
            warnings.append("sparse_samples")

    insufficient = bool(
        method is None
        or reference_bpm is None
        or result.samples_timed == 0
        or result.samples_with_hr == 0
        or result.total_hr_s <= 0
    )

    status = "insufficient" if insufficient else "ok"
    buckets = result.buckets if not insufficient else []
    cuts_bpm = result.cuts_bpm if not insufficient else []
    cuts_pct = result.cuts_pct if not insufficient else []
    coverage = (
        round(result.samples_with_hr / result.samples_timed, 3) if result.samples_timed else 0.0
    )

    return HrZonesOut(
        activity_id=activity.id,
        status=status,
        method=method,
        source=source,
        reference_bpm=reference_bpm,
        cuts_bpm=cuts_bpm,
        cuts_pct=cuts_pct,
        zones=[
            HrZoneOut(
                key=bucket.key,
                lower_bpm=bucket.lower_bpm,
                upper_bpm=bucket.upper_bpm,
                lower_pct=bucket.lower_pct,
                upper_pct=bucket.upper_pct,
                seconds=round(bucket.seconds, 1),
                percentage=round(bucket.percentage, 1),
            )
            for bucket in buckets
        ],
        total_hr_s=round(result.total_hr_s, 1),
        activity_duration_s=round(activity.duration_s or 0.0, 1),
        samples_total=result.samples_total,
        samples_timed=result.samples_timed,
        samples_with_hr=result.samples_with_hr,
        coverage=coverage,
        avg_hr=result.avg_hr,
        avg_hr_source=result.avg_hr_source,
        max_hr=result.max_hr,
        max_hr_source=result.max_hr_source,
        stream_max_hr=result.stream_max_hr,
        warnings=warnings,
        notes=notes,
        model_version=MODEL_VERSION,
    )


def _resolve_reference(
    activity: Activity,
    settings: ResolvedAnalysisSettings,
    stream_max: int | None,
) -> tuple[str | None, str | None, int | None]:
    """Pick the reference and say where it came from."""

    manual = settings.manual
    observed = settings.observed

    if manual.threshold_hr is not None:
        return "threshold_hr", "manual", int(manual.threshold_hr)
    if manual.max_hr is not None:
        return "max_hr", "manual", int(manual.max_hr)
    if observed.max_hr is not None:
        return "max_hr", "observed", int(observed.max_hr)
    if activity.max_hr is not None:
        return "max_hr", "activity_fallback", int(activity.max_hr)
    if stream_max is not None:
        return "max_hr", "activity_fallback", int(stream_max)
    return None, None, None


def _calculate(
    samples: list[StreamTime],
    activity: Activity,
    method: str | None,
    reference_bpm: int | None,
) -> ZoneResult:
    result = ZoneResult(samples_total=len(samples))
    offsets = _offsets(samples)
    result.samples_timed = sum(1 for value in offsets if value is not None)
    deltas = _deltas(offsets)

    heart_rates = [sample.heart_rate for sample in samples]
    valid_hrs = [
        int(hr) for hr in heart_rates if hr is not None and MIN_VALID_HR <= hr <= MAX_VALID_HR
    ]
    result.clipped_samples = sum(
        1 for hr in heart_rates if hr is not None and not MIN_VALID_HR <= hr <= MAX_VALID_HR
    )
    result.stream_max_hr = max(valid_hrs) if valid_hrs else None
    result.samples_with_hr = sum(
        1
        for sample, offset in zip(samples, offsets, strict=True)
        if offset is not None
        and sample.heart_rate is not None
        and MIN_VALID_HR <= sample.heart_rate <= MAX_VALID_HR
    )

    result.avg_hr, result.avg_hr_source = _average_hr(activity, samples, offsets, deltas)
    result.max_hr, result.max_hr_source = _activity_max(activity, result.stream_max_hr)

    if method is None or reference_bpm is None:
        return result

    result.cuts_pct = list(THRESHOLD_HR_CUT_PCTS if method == "threshold_hr" else MAX_HR_CUT_PCTS)
    result.cuts_bpm = _cuts_bpm(reference_bpm, result.cuts_pct)
    result.buckets = _buckets(result.cuts_bpm, result.cuts_pct)

    for index, delta in enumerate(deltas):
        if delta is None:
            result.gaps_skipped += 1
            continue
        heart_rate = samples[index].heart_rate
        if heart_rate is None or not MIN_VALID_HR <= heart_rate <= MAX_VALID_HR:
            continue
        bucket = result.buckets[_zone_index(heart_rate, result.cuts_bpm)]
        bucket.seconds += delta
        result.total_hr_s += delta

    if result.total_hr_s > 0:
        for bucket in result.buckets:
            bucket.percentage = bucket.seconds / result.total_hr_s * 100.0

    return result


def _offsets(samples: list[StreamTime]) -> list[float | None]:
    first_timestamp = next(
        (sample.timestamp_utc for sample in samples if sample.timestamp_utc), None
    )
    offsets: list[float | None] = []
    for sample in samples:
        if sample.elapsed_s is not None:
            offsets.append(float(sample.elapsed_s))
        elif sample.timestamp_utc is not None and first_timestamp is not None:
            offsets.append((sample.timestamp_utc - first_timestamp).total_seconds())
        else:
            offsets.append(None)
    return offsets


def _deltas(offsets: list[float | None]) -> list[float | None]:
    deltas: list[float | None] = []
    previous_delta: float | None = None
    last_timed = max(
        (index for index, offset in enumerate(offsets) if offset is not None),
        default=None,
    )
    for index, offset in enumerate(offsets):
        nxt = offsets[index + 1] if index + 1 < len(offsets) else None
        delta: float | None = None
        if offset is not None and nxt is not None:
            delta = nxt - offset
        if delta is None and index == last_timed:
            delta = previous_delta
        if delta is not None and 0.0 < delta <= MAX_SAMPLE_DELTA_S:
            deltas.append(delta)
            previous_delta = delta
        else:
            deltas.append(None)
    return deltas


def _cuts_bpm(reference_bpm: int, pcts: list[float]) -> list[int]:
    cuts: list[int] = []
    for index, pct in enumerate(pcts):
        value = int(reference_bpm * pct / 100.0 + 0.5)
        # Keep the last internal cut free for the open top of zone 5.
        ceiling = MAX_VALID_HR if index == len(pcts) - 1 else MAX_VALID_HR - 1
        value = max(MIN_VALID_HR + 1, min(ceiling, value))
        if cuts:
            value = max(value, cuts[-1] + 1)
        cuts.append(min(value, MAX_VALID_HR))
    return cuts


def _buckets(cuts: list[int], pcts: list[float]) -> list[ZoneBucket]:
    buckets: list[ZoneBucket] = []
    lower = MIN_VALID_HR
    for index, key in enumerate(ZONE_KEYS):
        upper = cuts[index] if index < len(cuts) else MAX_VALID_HR
        buckets.append(
            ZoneBucket(
                key=key,
                lower_bpm=lower,
                upper_bpm=upper,
                lower_pct=None if index == 0 else pcts[index - 1],
                upper_pct=None if index == len(cuts) else pcts[index],
            )
        )
        lower = upper
    return buckets


def _zone_index(heart_rate: int, cuts: list[int]) -> int:
    for index, cut in enumerate(cuts):
        if heart_rate < cut:
            return index
    return len(cuts)


def _average_hr(
    activity: Activity,
    samples: list[StreamTime],
    offsets: list[float | None],
    deltas: list[float | None],
) -> tuple[int | None, str | None]:
    if activity.avg_hr is not None:
        return int(activity.avg_hr), "activity"
    weighted = 0.0
    seconds = 0.0
    for sample, delta in zip(samples, deltas, strict=True):
        if (
            delta is None
            or sample.heart_rate is None
            or not MIN_VALID_HR <= sample.heart_rate <= MAX_VALID_HR
        ):
            continue
        weighted += sample.heart_rate * delta
        seconds += delta
    if seconds > 0:
        return int(round(weighted / seconds)), "stream"
    # A sample without a usable interval still carries a heart rate.
    values = [
        sample.heart_rate
        for sample, offset in zip(samples, offsets, strict=True)
        if offset is not None
        and sample.heart_rate is not None
        and MIN_VALID_HR <= sample.heart_rate <= MAX_VALID_HR
    ]
    if values:
        return int(round(sum(values) / len(values))), "stream"
    return None, None


def _activity_max(activity: Activity, stream_max: int | None) -> tuple[int | None, str | None]:
    if activity.max_hr is not None:
        return int(activity.max_hr), "activity"
    if stream_max is not None:
        return stream_max, "stream"
    return None, None


def _stream_max(samples: list[StreamTime]) -> int | None:
    values = [
        sample.heart_rate
        for sample in samples
        if sample.heart_rate is not None and MIN_VALID_HR <= sample.heart_rate <= MAX_VALID_HR
    ]
    return max(values) if values else None


def _insufficient(
    activity: Activity,
    *,
    method: str | None,
    source: str | None,
    reference_bpm: int | None,
    warnings: list[str],
    notes: list[str],
    samples_total: int,
) -> HrZonesOut:
    return HrZonesOut(
        activity_id=activity.id,
        status="insufficient",
        method=method,
        source=source,
        reference_bpm=reference_bpm,
        cuts_bpm=[],
        cuts_pct=[],
        zones=[],
        total_hr_s=0.0,
        activity_duration_s=round(activity.duration_s or 0.0, 1),
        samples_total=samples_total,
        samples_timed=0,
        samples_with_hr=0,
        coverage=0.0,
        avg_hr=int(activity.avg_hr) if activity.avg_hr is not None else None,
        avg_hr_source="activity" if activity.avg_hr is not None else None,
        max_hr=int(activity.max_hr) if activity.max_hr is not None else None,
        max_hr_source="activity" if activity.max_hr is not None else None,
        stream_max_hr=None,
        warnings=warnings,
        notes=notes,
        model_version=MODEL_VERSION,
    )
