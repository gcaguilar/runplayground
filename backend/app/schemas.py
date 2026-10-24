"""API contracts. FastAPI publishes these as OpenAPI for the TypeScript client."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Activities


class SourceOut(ApiModel):
    source: str
    external_id: str
    original_filename: str | None = None
    imported_at: datetime
    parser_version: str | None = None
    raw_filename: str | None = None
    raw_sha256: str | None = None
    raw_size_bytes: int | None = None

    @classmethod
    def from_orm_source(cls, source: Any) -> SourceOut:
        raw = source.raw_file
        return cls(
            source=source.source,
            external_id=source.external_id,
            original_filename=source.original_filename,
            imported_at=source.imported_at,
            parser_version=source.parser_version,
            raw_filename=raw.filename if raw else None,
            raw_sha256=raw.sha256 if raw else None,
            raw_size_bytes=raw.size_bytes if raw else None,
        )


class LapOut(ApiModel):
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


class ActivityOut(ApiModel):
    id: int
    name: str
    description: str | None = None
    sport: str
    sub_sport: str | None = None
    start_time_utc: datetime
    distance_m: float
    duration_s: float
    moving_s: float | None = None
    elapsed_s: float | None = None
    avg_pace_s_per_km: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence_spm: float | None = None
    max_cadence_spm: float | None = None
    avg_power_w: float | None = None
    max_power_w: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    calories: float | None = None
    training_effect: float | None = None
    training_load: float | None = None
    device_name: str | None = None
    manufacturer: str | None = None
    is_race: bool
    has_streams: bool
    has_gps: bool
    has_laps: bool
    source_names: list[str] = Field(default_factory=list)
    primary_source: str | None = None
    quality_flag_list: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ActivityDetail(ActivityOut):
    laps: list[LapOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)


class ActivityList(ApiModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int


class StreamPoint(ApiModel):
    t: float | None = None
    distance_m: float | None = None
    heart_rate: int | None = None
    cadence_spm: float | None = None
    speed_mps: float | None = None
    elevation_m: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    power_w: float | None = None
    temperature_c: float | None = None


class ActivityStreams(ApiModel):
    activity_id: int
    total_points: int
    downsampled: bool
    points: list[StreamPoint]


class ActivityPatch(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    is_race: bool | None = None


# ---------------------------------------------------------------------------
# Weekly summary


class WeeklyTotals(ApiModel):
    activities: int
    distance_m: float
    duration_s: float
    elevation_gain_m: float
    active_days: int
    avg_hr: float | None = None
    longest_distance_m: float
    longest_duration_s: float


class WeeklyDay(ApiModel):
    date: date
    activities: int
    distance_m: float
    duration_s: float


class SportTotal(ApiModel):
    sport: str
    activities: int
    distance_m: float
    duration_s: float


class WeeklySummary(ApiModel):
    week_start: date
    week_end: date
    totals: WeeklyTotals
    previous: WeeklyTotals
    delta: dict[str, float | None]
    days: list[WeeklyDay]
    by_sport: list[SportTotal]


# ---------------------------------------------------------------------------
# Audit


class AuditFinding(ApiModel):
    code: str
    severity: Literal["critical", "warning", "info"]
    count: int | None = None
    activity_ids: list[int] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    message: str
    hint: str | None = None


class AuditCoverage(ApiModel):
    total_activities: int
    with_streams: int
    with_gps: int
    with_hr: int
    with_laps: int
    with_power: int
    pct_streams: float
    pct_gps: float
    pct_hr: float
    first_activity: datetime | None = None
    last_activity: datetime | None = None
    by_year: list[dict[str, int]] = Field(default_factory=list)
    by_source: list[dict[str, int | str]] = Field(default_factory=list)


class MissingActivity(ApiModel):
    id: int
    name: str
    sport: str
    start_time_utc: datetime
    missing: list[str]


class RaceCandidate(ApiModel):
    id: int
    name: str
    sport: str
    start_time_utc: datetime
    distance_m: float
    duration_s: float


class AuditReport(ApiModel):
    score: int
    generated_at: datetime
    findings: list[AuditFinding]
    coverage: AuditCoverage
    recent_missing: list[MissingActivity]
    race_candidates: list[RaceCandidate]
    last_sync: dict[str, Any] | None = None
    garmin_configured: bool


# ---------------------------------------------------------------------------
# Sync / imports


class SyncRunOut(ApiModel):
    id: int
    kind: str
    mode: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    activities_seen: int
    activities_created: int
    activities_updated: int
    activities_skipped: int
    files_downloaded: int
    errors_count: int
    message: str | None = None
    errors: list[str] = Field(default_factory=list)


class SyncStatus(ApiModel):
    running: bool
    current_run_id: int | None = None
    mode: str | None = None
    last_run: SyncRunOut | None = None
    interval_hours: int
    next_sync_at: datetime | None = None
    garmin_configured: bool
    token: dict[str, Any]


class StartSyncRequest(ApiModel):
    mode: Literal["incremental", "backfill"] = "incremental"


class StartSyncResponse(ApiModel):
    started: bool
    run_id: int | None = None
    message: str


class ImportFileResult(ApiModel):
    filename: str
    status: str
    activity_id: int | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportResponse(ApiModel):
    run_id: int
    results: list[ImportFileResult]


class ImportRunOut(ApiModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    message: str | None = None
    results: list[ImportFileResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System / auth


class HealthResponse(ApiModel):
    status: str
    version: str


class AuthStatus(ApiModel):
    auth_mode: Literal["none", "password"]
    authenticated: bool


class LoginRequest(ApiModel):
    password: str = Field(min_length=1, max_length=200)


class GarminTokenStatus(ApiModel):
    configured: bool
    cached: bool
    expires_at: float | None = None
    expires_in_seconds: int | None = None


class SystemStatus(ApiModel):
    app_name: str
    version: str
    auth_mode: str
    garmin_configured: bool
    garmin_key_fingerprint: str | None = None
    garmin_token: GarminTokenStatus
    activity_count: int
    raw_file_count: int
    database_size_bytes: int
    data_dir: str
    sync_interval_hours: int
    last_sync: dict[str, Any] | None = None
    supported_formats: list[str]
