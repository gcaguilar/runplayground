"""Data quality audit: what exists, what is missing, what looks wrong."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.models import Activity
from app.schemas import (
    AuditCoverage,
    AuditFinding,
    AuditReport,
    MissingActivity,
    RaceCandidate,
)
from app.services.state import get_state
from app.services.sync import stale_sync_threshold
from app.utils import is_running, utcnow

router = APIRouter(prefix="/audit", tags=["audit"])

RACE_WORDS = (
    "race",
    "carrera",
    "maraton",
    "maratón",
    "marathon",
    "media maraton",
    "media maratón",
    "half marathon",
    "10k",
    "5k",
    "21k",
    "42k",
)


@router.get("", response_model=AuditReport)
def audit(db: Session = Depends(get_db)) -> AuditReport:
    settings = get_settings()
    activities = list(
        db.scalars(
            select(Activity)
            .options(selectinload(Activity.sources))
            .order_by(Activity.start_time_utc.desc())
        ).all()
    )
    total = len(activities)

    with_streams = sum(1 for activity in activities if activity.has_streams)
    with_gps = sum(1 for activity in activities if activity.has_gps)
    with_hr = sum(1 for activity in activities if activity.avg_hr is not None)
    with_laps = sum(1 for activity in activities if activity.has_laps)
    with_power = sum(1 for activity in activities if activity.avg_power_w is not None)

    pct_streams = round(with_streams / total * 100, 1) if total else 0.0
    pct_gps = round(with_gps / total * 100, 1) if total else 0.0
    pct_hr = round(with_hr / total * 100, 1) if total else 0.0

    by_year_counter = Counter(activity.start_time_utc.year for activity in activities)
    by_year = [
        {"year": year, "activities": count}
        for year, count in sorted(by_year_counter.items(), reverse=True)
    ]

    source_counter: dict[str, int] = Counter()
    for activity in activities:
        for source in activity.source_names:
            source_counter[source] += 1
    by_source: list[dict[str, int | str]] = [
        {"source": source, "activities": count} for source, count in source_counter.most_common()
    ]

    sync_state = get_state(db, "sync", {})
    last_sync = sync_state or None
    garmin_configured = settings.garmin_configured

    findings: list[AuditFinding] = []
    score = 100

    if not garmin_configured:
        findings.append(
            AuditFinding(
                code="no_garmin_key",
                severity="info",
                message="No Garmin Personal API key is configured.",
                hint="Add GARMIN_PERSONAL_API_KEY to .env to sync activities automatically.",
            )
        )
        score -= 5

    if total == 0:
        findings.append(
            AuditFinding(
                code="no_activities",
                severity="critical",
                message="There are no activities in the database.",
                hint="Configure the Garmin key and run a sync, or import FIT/TCX/GPX files.",
            )
        )
        score -= 40
    else:
        if with_streams < total:
            count = total - with_streams
            findings.append(
                AuditFinding(
                    code="missing_streams",
                    severity="warning" if pct_streams < 90 else "info",
                    count=count,
                    activity_ids=[a.id for a in activities if not a.has_streams][:50],
                    params={"count": count, "pct": pct_streams},
                    message=f"{count} activities have no per-second stream.",
                    hint="Re-sync with FIT download enabled or import the original files.",
                )
            )
            score -= round((1 - with_streams / total) * 25)

        if with_hr < total:
            count = total - with_hr
            findings.append(
                AuditFinding(
                    code="missing_hr",
                    severity="warning" if pct_hr < 80 else "info",
                    count=count,
                    activity_ids=[a.id for a in activities if a.avg_hr is None][:50],
                    params={"count": count, "pct": pct_hr},
                    message=f"{count} activities have no heart-rate summary.",
                    hint="Heart rate is required for intensity and load analysis.",
                )
            )
            score -= round((1 - with_hr / total) * 10)

        if with_gps < total:
            count = total - with_gps
            findings.append(
                AuditFinding(
                    code="missing_gps",
                    severity="info",
                    count=count,
                    activity_ids=[a.id for a in activities if not a.has_gps][:50],
                    params={"count": count, "pct": pct_gps},
                    message=f"{count} activities have no GPS track (indoor or stripped files).",
                    hint="Missing GPS is expected for treadmill and indoor activities.",
                )
            )

        if not any(activity.is_race for activity in activities):
            findings.append(
                AuditFinding(
                    code="no_races",
                    severity="info",
                    message="No activity has been confirmed as an official race.",
                    hint="Race results will improve prediction confidence once available.",
                )
            )

        speed_outliers = [
            activity
            for activity in activities
            if is_running(activity.sport)
            and (
                (activity.avg_speed_mps or 0) > 7.0
                or (activity.max_speed_mps or 0) > 12.5
                or (
                    activity.distance_m > 0
                    and activity.duration_s > 0
                    and activity.avg_pace_s_per_km
                    and activity.avg_pace_s_per_km < 150
                )
            )
        ]
        if speed_outliers:
            findings.append(
                AuditFinding(
                    code="implausible_speed",
                    severity="warning",
                    count=len(speed_outliers),
                    activity_ids=[a.id for a in speed_outliers][:50],
                    params={"count": len(speed_outliers)},
                    message=(
                        f"{len(speed_outliers)} running activities have implausible speed values."
                    ),
                    hint="Check the source file; these values should not feed predictions.",
                )
            )
            score -= min(10, len(speed_outliers) * 2)

        hr_outliers = [
            activity
            for activity in activities
            if (activity.max_hr or 0) > 230
            or (activity.avg_hr or 0) > 220
            or (activity.avg_hr is not None and activity.avg_hr < 30)
            or (
                activity.avg_hr is not None
                and activity.max_hr is not None
                and activity.avg_hr > activity.max_hr
            )
        ]
        if hr_outliers:
            findings.append(
                AuditFinding(
                    code="implausible_hr",
                    severity="warning",
                    count=len(hr_outliers),
                    activity_ids=[a.id for a in hr_outliers][:50],
                    params={"count": len(hr_outliers)},
                    message=f"{len(hr_outliers)} activities have implausible heart-rate values.",
                    hint="Verify the device configuration and the original file.",
                )
            )
            score -= min(10, len(hr_outliers) * 2)

        future = [
            activity
            for activity in activities
            if activity.start_time_utc > utcnow() + timedelta(hours=1)
        ]
        if future:
            findings.append(
                AuditFinding(
                    code="future_activity",
                    severity="warning",
                    count=len(future),
                    activity_ids=[a.id for a in future][:50],
                    params={"count": len(future)},
                    message=f"{len(future)} activities are dated in the future.",
                    hint="Check the timezone or the device clock.",
                )
            )
            score -= 5

        duplicate_ids = _duplicate_candidates(activities)
        if duplicate_ids:
            findings.append(
                AuditFinding(
                    code="duplicate_candidates",
                    severity="warning",
                    count=len(duplicate_ids),
                    activity_ids=duplicate_ids[:50],
                    params={"count": len(duplicate_ids)},
                    message=f"{len(duplicate_ids)} activities look like possible duplicates.",
                    hint="Review and delete the duplicate copies if they are the same session.",
                )
            )
            score -= min(10, len(duplicate_ids) * 2)

    if total > 0:
        if garmin_configured and not sync_state:
            findings.append(
                AuditFinding(
                    code="never_synced",
                    severity="warning",
                    message="The Garmin key is configured but no sync has completed yet.",
                    hint="Run an incremental sync.",
                )
            )
            score -= 10
        elif sync_state:
            last_finished = sync_state.get("last_finished_at")
            if last_finished:
                try:
                    finished = datetime.fromisoformat(last_finished)
                    if utcnow() - finished > stale_sync_threshold(settings):
                        findings.append(
                            AuditFinding(
                                code="stale_sync",
                                severity="warning",
                                params={"last_sync": last_finished},
                                message="The last Garmin sync is older than expected.",
                                hint="Check the container scheduler or run a sync manually.",
                            )
                        )
                        score -= 10
                except ValueError:
                    pass
            if sync_state.get("last_status") == "error":
                findings.append(
                    AuditFinding(
                        code="last_sync_failed",
                        severity="warning",
                        message="The last Garmin sync ended with an error.",
                        hint="Open Settings to read the error and verify the API key.",
                    )
                )
                score -= 5

    race_candidates = [
        RaceCandidate(
            id=activity.id,
            name=activity.name,
            sport=activity.sport,
            start_time_utc=activity.start_time_utc,
            distance_m=activity.distance_m,
            duration_s=activity.duration_s,
        )
        for activity in activities
        if not activity.is_race and is_running(activity.sport) and _looks_like_race(activity.name)
    ][:10]
    if race_candidates:
        findings.append(
            AuditFinding(
                code="race_candidates",
                severity="info",
                count=len(race_candidates),
                activity_ids=[candidate.id for candidate in race_candidates],
                params={"count": len(race_candidates)},
                message="Some activities look like races but are not confirmed.",
                hint="Open an activity and mark it as an official race if it applies.",
            )
        )

    recent_missing = []
    for activity in activities[:20]:
        missing = []
        if not activity.has_streams:
            missing.append("streams")
        if activity.avg_hr is None:
            missing.append("heart_rate")
        if (
            is_running(activity.sport)
            and activity.sub_sport not in {"treadmill_running", "indoor_running"}
            and not activity.has_gps
        ):
            missing.append("gps")
        if missing:
            recent_missing.append(
                MissingActivity(
                    id=activity.id,
                    name=activity.name,
                    sport=activity.sport,
                    start_time_utc=activity.start_time_utc,
                    missing=missing,
                )
            )
        if len(recent_missing) >= 10:
            break

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda finding: severity_order.get(finding.severity, 3))

    return AuditReport(
        score=max(0, min(100, score)),
        generated_at=utcnow(),
        findings=findings,
        coverage=AuditCoverage(
            total_activities=total,
            with_streams=with_streams,
            with_gps=with_gps,
            with_hr=with_hr,
            with_laps=with_laps,
            with_power=with_power,
            pct_streams=pct_streams,
            pct_gps=pct_gps,
            pct_hr=pct_hr,
            first_activity=activities[-1].start_time_utc if activities else None,
            last_activity=activities[0].start_time_utc if activities else None,
            by_year=by_year,
            by_source=by_source,
        ),
        recent_missing=recent_missing,
        race_candidates=race_candidates,
        last_sync=last_sync,
        garmin_configured=garmin_configured,
    )


def _duplicate_candidates(activities: list[Activity]) -> list[int]:
    groups: dict[tuple, list[Activity]] = defaultdict(list)
    for activity in activities:
        groups[
            (
                activity.sport,
                activity.start_time_utc.date(),
                int(round(activity.distance_m / 100)),
            )
        ].append(activity)
    duplicates: list[int] = []
    for group in groups.values():
        if len(group) > 1:
            ordered = sorted(group, key=lambda item: item.id)
            duplicates.extend(activity.id for activity in ordered[1:])
    return duplicates


def _looks_like_race(name: str) -> bool:
    lowered = (name or "").lower()
    return any(word in lowered for word in RACE_WORDS)
