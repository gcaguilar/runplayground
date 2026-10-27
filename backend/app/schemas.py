"""API contracts. FastAPI publishes these as OpenAPI for the TypeScript client."""

from __future__ import annotations

from datetime import date, datetime
from datetime import date as Date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    intensity_override: str | None = None
    rpe: int | None = None
    has_streams: bool
    has_gps: bool
    has_laps: bool
    source_names: list[str] = Field(default_factory=list)
    primary_source: str | None = None
    quality_flag_list: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ActivityClassificationOut(ApiModel):
    key: str
    auto_key: str
    source: Literal["manual", "auto"]
    overridden: bool
    mode: Literal["auto", "pace", "hr"]
    threshold_pace_s_per_km: float | None = None
    hr_reference: float | None = None


class ActivityDetail(ActivityOut):
    laps: list[LapOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    classification: ActivityClassificationOut | None = None


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


# ---------------------------------------------------------------------------
# Workout comparison (M7)


class ComparisonSideOut(ApiModel):
    activity_id: int
    name: str
    sport: str
    sub_sport: str | None = None
    start_time_utc: datetime
    distance_m: float
    duration_s: float
    pace_s_per_km: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    cadence_spm: float | None = None
    power_w: float | None = None
    elevation_gain_m: float | None = None
    is_race: bool
    has_streams: bool
    has_gps: bool
    training_effect: float | None = None
    training_load: float | None = None


class ComparisonMetricOut(ApiModel):
    key: str
    left: float | None = None
    right: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    direction: str = "context"
    better: str = "unknown"


class ComparisonSplitOut(ApiModel):
    index: int
    distance_m: float
    left_pace_s_per_km: float | None = None
    right_pace_s_per_km: float | None = None
    left_hr: int | None = None
    right_hr: int | None = None
    pace_delta_s: float | None = None


class ComparisonInsightOut(ApiModel):
    key: str
    value: float | None = None
    params: dict[str, float | int | str | None] = Field(default_factory=dict)


class ComparisonView(ApiModel):
    generated_at: datetime
    model_version: str
    status: str
    comparability: float
    left: ComparisonSideOut
    right: ComparisonSideOut
    metrics: list[ComparisonMetricOut] = Field(default_factory=list)
    splits: list[ComparisonSplitOut] = Field(default_factory=list)
    insights: list[ComparisonInsightOut] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ActivityPatch(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    is_race: bool | None = None
    intensity_override: Literal["easy", "moderate", "hard"] | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)


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


# ---------------------------------------------------------------------------
# Performance


class EffortOut(ApiModel):
    activity_id: int
    activity_name: str
    start_time_utc: datetime
    distance_m: float
    duration_s: float
    pace_s_per_km: float
    method: str
    is_full_activity: bool
    is_race: bool
    has_gps: bool
    quality: float
    segment_start_s: float
    segment_end_s: float


class GoalOut(ApiModel):
    distance_m: float
    target_time_s: float
    target_date: date | None = None
    race_name: str | None = None
    notes: str | None = None
    updated_at: datetime


class GoalUpsert(ApiModel):
    target_time_s: float = Field(gt=0, le=24 * 3600)
    target_date: date | None = None
    race_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)


class PredictionEstimateOut(ApiModel):
    time_s: float
    low_s: float
    high_s: float
    pace_s_per_km: float
    method: str
    sigma: float
    source_efforts: list[EffortOut] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class DistancePredictionOut(ApiModel):
    distance_key: str
    distance_m: float
    status: str
    official_pr: EffortOut | None = None
    recent_best: EffortOut | None = None
    goal: GoalOut | None = None
    ceiling: PredictionEstimateOut | None = None
    planning: PredictionEstimateOut | None = None
    gap_s: float | None = None
    gap_pct: float | None = None
    goal_gap_s: float | None = None
    goal_gap_pct: float | None = None
    confidence: str
    confidence_score: float
    confidence_reasons: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class FitnessAnchorOut(ApiModel):
    distance_m: float
    time_s: float
    low_s: float
    high_s: float
    pace_s_per_km: float
    confidence: str
    confidence_score: float
    as_of: datetime


class PerformanceDataSummary(ApiModel):
    running_activities: int
    activities_with_streams: int
    efforts: int
    races: int
    first_effort_at: datetime | None = None
    last_effort_at: datetime | None = None


class PreparationSummary(ApiModel):
    longest_run_90d_m: float | None = None
    weekly_distance_28d_m: float | None = None
    races_365d: int
    efforts_365d: int


class GarminMetricPoint(ApiModel):
    date: date
    value: float


class GarminRacePrediction(ApiModel):
    date: date
    distance_m: float
    time_s: float


class GarminReference(ApiModel):
    imported_at: datetime | None = None
    vo2max: GarminMetricPoint | None = None
    vo2max_series: list[GarminMetricPoint] = Field(default_factory=list)
    readiness: GarminMetricPoint | None = None
    acute_training_load: GarminMetricPoint | None = None
    chronic_training_load: GarminMetricPoint | None = None
    race_predictions: list[GarminRacePrediction] = Field(default_factory=list)


class PerformanceOverview(ApiModel):
    generated_at: datetime
    model_version: str
    window_days: int
    recent_days: int
    status: str
    fitness_anchor: FitnessAnchorOut | None = None
    distances: list[DistancePredictionOut]
    data: PerformanceDataSummary
    preparation: PreparationSummary
    garmin: GarminReference
    warnings: list[str] = Field(default_factory=list)


class SnapshotPredictionOut(ApiModel):
    distance_key: str
    distance_m: float
    planning_s: float | None = None
    planning_low_s: float | None = None
    planning_high_s: float | None = None
    confidence: str | None = None


class PerformanceSnapshotOut(ApiModel):
    date: date
    computed_at: datetime
    fitness_anchor_s: float | None = None
    fitness_anchor_low_s: float | None = None
    fitness_anchor_high_s: float | None = None
    fitness_confidence: str | None = None
    predictions: list[SnapshotPredictionOut] = Field(default_factory=list)


class PerformanceHistory(ApiModel):
    items: list[PerformanceSnapshotOut]
    days: int


class PerformanceRecomputeResponse(ApiModel):
    activities: int
    efforts: int
    overview: PerformanceOverview


class GarminExportResponse(ApiModel):
    run_id: int
    status: str
    files_scanned: int
    metrics_imported: int
    metrics_skipped: int
    activities_imported: int
    activities_merged: int
    activities_skipped: int
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diagnostics and training (M2)


class DimensionOut(ApiModel):
    key: str
    score: float | None = None
    status: str
    confidence: str
    confidence_score: float
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class LimiterOut(ApiModel):
    dimension_key: str
    priority: int
    score: float
    impact: float
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class IntensityBucketOut(ApiModel):
    key: str
    sessions: int
    duration_s: float
    distance_m: float
    share: float


class IntensityTargetOut(ApiModel):
    key: str
    low: float
    high: float


class IntensityOut(ApiModel):
    buckets: list[IntensityBucketOut]
    targets: list[IntensityTargetOut]
    classified_sessions: int
    unknown_sessions: int
    score: float | None = None
    status: str
    reasons: list[str] = Field(default_factory=list)


class WeeklyLoadOut(ApiModel):
    week_start: date
    distance_m: float
    duration_s: float
    load: float
    sessions: int


class LoadOut(ApiModel):
    weekly: list[WeeklyLoadOut]
    acute_7d: float
    chronic_weekly: float
    ratio: float | None = None
    ramp_pct: float | None = None
    score: float | None = None
    status: str
    reasons: list[str] = Field(default_factory=list)


class AnalysisCoverageOut(ApiModel):
    activities: int
    weeks_with_data: int
    window_weeks: int
    first_activity_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_race_at: datetime | None = None
    has_anchor: bool
    anchor_pace_s_per_km: float | None = None
    has_hr: bool
    trail_share: float
    readiness_days: int


class AnalysisReferenceOut(ApiModel):
    imported_at: datetime | None = None
    readiness_28d: float | None = None
    acute_load: float | None = None
    chronic_load: float | None = None


class DiagnosticsOverview(ApiModel):
    generated_at: datetime
    model_version: str
    window_days: int
    status: str
    score: float | None = None
    headline: str
    confidence: str
    confidence_score: float
    goal: GoalOut | None = None
    dimensions: list[DimensionOut]
    limiters: list[LimiterOut]
    intensity: IntensityOut
    load: LoadOut
    coverage: AnalysisCoverageOut
    reference: AnalysisReferenceOut
    warnings: list[str] = Field(default_factory=list)


class TrainingFocusOut(ApiModel):
    dimension_key: str
    priority: int
    score: float | None = None
    action: str
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class TrainingSessionOut(ApiModel):
    type: str
    intensity: str
    priority: str
    duration_low_s: float | None = None
    duration_high_s: float | None = None
    distance_low_m: float | None = None
    distance_high_m: float | None = None
    purpose: str


class TrainingLoadTargetOut(ApiModel):
    weekly_distance_low_m: float
    weekly_distance_high_m: float
    current_weekly_distance_m: float
    long_run_low_m: float
    long_run_high_m: float
    quality_sessions_low: int
    quality_sessions_high: int


ClassificationMode = Literal["auto", "pace", "hr"]


class AnalysisSettingsValuesOut(ApiModel):
    max_hr: int | None = None
    resting_hr: int | None = None
    threshold_hr: int | None = None
    threshold_pace_s_per_km: float | None = None
    classification_mode: ClassificationMode | None = None


class AnalysisSettingsOut(ApiModel):
    observed: AnalysisSettingsValuesOut
    manual: AnalysisSettingsValuesOut
    effective: AnalysisSettingsValuesOut
    sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AnalysisSettingsUpdate(ApiModel):
    max_hr: int | None = Field(default=None, ge=100, le=230)
    resting_hr: int | None = Field(default=None, ge=30, le=120)
    threshold_hr: int | None = Field(default=None, ge=100, le=230)
    threshold_pace_s_per_km: float | None = Field(default=None, ge=120, le=1200)
    classification_mode: ClassificationMode | None = None

    @model_validator(mode="after")
    def _coherent(self) -> AnalysisSettingsUpdate:
        if (
            self.max_hr is not None
            and self.threshold_hr is not None
            and self.threshold_hr > self.max_hr
        ):
            raise ValueError("threshold_hr must be lower than or equal to max_hr")
        if (
            self.resting_hr is not None
            and self.threshold_hr is not None
            and self.resting_hr >= self.threshold_hr
        ):
            raise ValueError("resting_hr must be lower than threshold_hr")
        return self


class TrainingPlan(ApiModel):
    generated_at: datetime
    model_version: str
    status: str
    phase: str
    phase_reason: str
    weeks_to_goal: int | None = None
    goal: GoalOut | None = None
    confidence: str
    confidence_score: float
    focus: list[TrainingFocusOut]
    sessions: list[TrainingSessionOut]
    load_target: TrainingLoadTargetOut
    intensity: IntensityOut
    load: LoadOut
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Progress, calendar, reports and race planning (M3)


class ProgressTotalsOut(ApiModel):
    distance_m: float
    duration_s: float
    elevation_gain_m: float
    sessions: int
    active_days: int
    load: float


class ProgressWeekOut(ApiModel):
    week_start: date
    distance_m: float
    duration_s: float
    load: float
    sessions: int
    active_days: int


class ConsistencyOut(ApiModel):
    window_days: int
    weeks: int
    weeks_with_data: int
    active_days: int
    current_streak_days: int
    longest_streak_days: int
    weekly_average_m: float
    best_week_start: date | None = None
    best_week_m: float


class FitnessPointOut(ApiModel):
    date: date
    time_s: float
    low_s: float | None = None
    high_s: float | None = None
    confidence: str | None = None


class PersonalBestOut(ApiModel):
    distance_key: str
    distance_m: float
    time_s: float
    pace_s_per_km: float
    activity_id: int
    activity_name: str
    date: datetime
    is_race: bool


class GoalProgressOut(ApiModel):
    distance_key: str | None = None
    distance_m: float
    target_time_s: float
    target_date: date | None = None
    race_name: str | None = None
    current_time_s: float | None = None
    low_s: float | None = None
    high_s: float | None = None
    confidence: str | None = None
    gap_s: float | None = None
    gap_pct: float | None = None
    readiness_pct: float | None = None
    status: str


class ProgressHighlightOut(ApiModel):
    key: str
    date: Date | None = None
    value: float
    activity_id: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class PlannedRaceOut(ApiModel):
    id: int
    name: str
    race_date: date
    distance_m: float
    goal_time_s: float | None = None
    priority: str
    location: str | None = None
    notes: str | None = None
    status: str
    activity_id: int | None = None
    created_at: datetime
    updated_at: datetime
    days_to_race: int | None = None
    weeks_to_race: int | None = None
    phase: str | None = None
    phase_reason: str | None = None
    target_pace_s_per_km: float | None = None
    predicted_time_s: float | None = None
    predicted_low_s: float | None = None
    predicted_high_s: float | None = None
    prediction_confidence: str | None = None
    gap_s: float | None = None
    gap_pct: float | None = None
    readiness: str
    weekly_distance_low_m: float | None = None
    weekly_distance_high_m: float | None = None
    long_run_low_m: float | None = None
    long_run_high_m: float | None = None


class PlannedRaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    race_date: date
    distance_m: float = Field(gt=0, le=500_000)
    goal_time_s: float | None = Field(default=None, gt=0, le=48 * 3600)
    priority: Literal["A", "B", "C"] = "B"
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["planned", "completed", "cancelled"] = "planned"
    activity_id: int | None = Field(default=None, ge=1)


class PlannedRaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    race_date: date | None = None
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    goal_time_s: float | None = Field(default=None, gt=0, le=48 * 3600)
    priority: Literal["A", "B", "C"] | None = None
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["planned", "completed", "cancelled"] | None = None
    activity_id: int | None = Field(default=None, ge=1)


class CalendarEntryOut(ApiModel):
    id: str
    date: Date
    kind: Literal["activity", "race", "session"]
    title: str
    sport: str | None = None
    activity_id: int | None = None
    race_id: int | None = None
    distance_m: float | None = None
    duration_s: float | None = None
    intensity: str | None = None
    status: str | None = None
    is_race: bool = False


class CalendarDayOut(ApiModel):
    date: Date
    entries: list[CalendarEntryOut] = Field(default_factory=list)
    actual_distance_m: float = 0.0
    planned_distance_m: float = 0.0


class CalendarWeekOut(ApiModel):
    week_start: date
    days: list[CalendarDayOut]
    actual_distance_m: float
    planned_distance_m: float


class CalendarView(ApiModel):
    start: date
    end: date
    today: date
    weeks: list[CalendarWeekOut]


class ProgressOverview(ApiModel):
    generated_at: datetime
    window_days: int
    status: str
    totals: ProgressTotalsOut
    previous: ProgressTotalsOut
    delta: dict[str, float | None]
    consistency: ConsistencyOut
    weeks: list[ProgressWeekOut]
    fitness: list[FitnessPointOut]
    best_efforts: list[PersonalBestOut]
    goals: list[GoalProgressOut]
    races: list[PlannedRaceOut]
    highlights: list[ProgressHighlightOut]
    warnings: list[str] = Field(default_factory=list)


class AdherenceWeekOut(ApiModel):
    week_start: date
    phase: str
    status: str
    score: float | None = None
    volume_actual_m: float
    volume_low_m: float
    volume_high_m: float
    volume_status: str
    longest_actual_m: float
    long_run_low_m: float
    long_run_high_m: float
    long_run_status: str
    quality_actual: int
    quality_low: int
    quality_high: int
    quality_status: str
    rest_actual: int
    rest_planned: int
    rest_status: str
    sessions_actual: int
    sessions_planned: int
    active_days: int
    reasons: list[str] = Field(default_factory=list)


class AdherenceSummaryOut(ApiModel):
    weeks: int
    scored_weeks: int
    average_score: float | None = None
    current_score: float | None = None
    trend: str
    volume_ratio: float | None = None
    long_run_ratio: float | None = None
    quality_ratio: float | None = None
    rest_ratio: float | None = None


class AdherenceOverview(ApiModel):
    generated_at: datetime
    model_version: str
    weeks: int
    status: str
    current_week_start: date
    summary: AdherenceSummaryOut
    items: list[AdherenceWeekOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportNarrativeOut(ApiModel):
    key: str
    tone: str
    confidence: str
    confidence_score: float
    improvement: str | None = None
    limitation: str | None = None
    action: str | None = None
    fitness_change_s: float | None = None
    fitness_change_pct: float | None = None
    volume_delta_pct: float | None = None
    evidence: dict[str, float | int | str | None] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ReportOut(ApiModel):
    generated_at: datetime
    period: Literal["week", "month"]
    start: date
    end: date
    label: str
    totals: ProgressTotalsOut
    previous: ProgressTotalsOut
    delta: dict[str, float | None]
    narrative: ReportNarrativeOut
    days: list[WeeklyDay] = Field(default_factory=list)
    weeks: list[ProgressWeekOut] = Field(default_factory=list)
    by_sport: list[SportTotal] = Field(default_factory=list)
    load: LoadOut
    goals: list[GoalProgressOut] = Field(default_factory=list)
    races: list[PlannedRaceOut] = Field(default_factory=list)
    highlights: list[ProgressHighlightOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Future scenarios and continuous tracking (M4)


class ScenarioProjectionOut(ApiModel):
    distance_key: str
    distance_m: float
    time_s: float | None = None
    low_s: float | None = None
    high_s: float | None = None
    pace_s_per_km: float | None = None
    delta_s: float | None = None
    delta_pct: float | None = None
    confidence: str
    confidence_score: float


class ForecastGoalOut(ApiModel):
    distance_key: str
    distance_m: float
    name: str | None = None
    source: str
    target_time_s: float | None = None
    target_date: date | None = None
    days_to_target: int | None = None
    baseline_gap_s: float | None = None
    baseline_gap_pct: float | None = None
    baseline_status: str = "unknown"


class ForecastBaselineOut(ApiModel):
    anchor_time_s: float | None = None
    anchor_low_s: float | None = None
    anchor_high_s: float | None = None
    confidence: str
    confidence_score: float
    distances: list[ScenarioProjectionOut] = Field(default_factory=list)


class ScenarioOut(ApiModel):
    key: str
    assumptions: list[str] = Field(default_factory=list)
    evidence: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    effect_pct: float | None = None
    anchor_time_s: float | None = None
    anchor_low_s: float | None = None
    anchor_high_s: float | None = None
    delta_s: float | None = None
    delta_pct: float | None = None
    goal_gap_s: float | None = None
    goal_gap_pct: float | None = None
    goal_status: str = "unknown"
    confidence: str
    confidence_score: float
    confidence_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    distances: list[ScenarioProjectionOut] = Field(default_factory=list)


class ForecastView(ApiModel):
    generated_at: datetime
    model_version: str
    weeks: int
    status: str
    focus_distance_key: str
    focus_distance_m: float
    focus_source: str
    goal: ForecastGoalOut | None = None
    baseline: ForecastBaselineOut
    scenarios: list[ScenarioOut] = Field(default_factory=list)
    training: dict[str, float | int | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AccuracySampleOut(ApiModel):
    distance_key: str
    distance_m: float
    predicted_on: date
    actual_on: date
    horizon_days: int
    predicted_s: float
    predicted_low_s: float | None = None
    predicted_high_s: float | None = None
    actual_s: float
    activity_id: int
    activity_name: str
    is_race: bool
    error_s: float
    error_pct: float
    within_range: bool


class AccuracySummaryOut(ApiModel):
    scope: str
    key: str
    samples: int
    mean_bias_s: float
    mean_bias_pct: float
    mae_s: float
    mape_pct: float
    within_range_pct: float


class PredictionAccuracyOut(ApiModel):
    samples: list[AccuracySampleOut] = Field(default_factory=list)
    overall: AccuracySummaryOut | None = None
    by_distance: list[AccuracySummaryOut] = Field(default_factory=list)
    by_horizon: list[AccuracySummaryOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GoalHistoryPointOut(ApiModel):
    date: date
    predicted_s: float | None = None
    gap_s: float | None = None


class GoalResultOut(ApiModel):
    date: date
    time_s: float
    activity_id: int
    activity_name: str
    is_race: bool
    source: str


class GoalRevisionOut(ApiModel):
    created_at: datetime
    target_time_s: float
    target_date: date | None = None
    race_name: str | None = None
    prediction_time_s: float | None = None
    prediction_low_s: float | None = None
    prediction_high_s: float | None = None
    confidence: str | None = None
    change_s: float | None = None


class GoalTrackingOut(ApiModel):
    distance_key: str
    distance_m: float
    target_time_s: float
    target_date: date | None = None
    race_name: str | None = None
    current_time_s: float | None = None
    low_s: float | None = None
    high_s: float | None = None
    confidence: str | None = None
    gap_s: float | None = None
    gap_pct: float | None = None
    readiness_pct: float | None = None
    status: str
    trend: str
    change_28d_s: float | None = None
    change_28d_pct: float | None = None
    days_to_target: int | None = None
    last_reviewed_at: datetime
    history: list[GoalHistoryPointOut] = Field(default_factory=list)
    results: list[GoalResultOut] = Field(default_factory=list)
    revisions: list[GoalRevisionOut] = Field(default_factory=list)


class TrackedActionOut(ApiModel):
    dimension_key: str
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    baseline_score: float | None = None
    baseline_confidence: str | None = None
    current_score: float | None = None
    delta: float | None = None
    verdict: str
    reasons: list[str] = Field(default_factory=list)


class ActionUpsert(ApiModel):
    status: Literal["pending", "in_progress", "completed"]
    note: str | None = Field(default=None, max_length=2000)


class ActionSuggestionOut(ApiModel):
    dimension_key: str
    score: float | None = None
    priority: int | None = None
    action: str
    reasons: list[str] = Field(default_factory=list)
    tracked: bool = False


class DriverOut(ApiModel):
    key: str
    correlation: float | None = None
    direction: str
    strength: str
    samples: int
    improvement_high_pct: float | None = None
    improvement_low_pct: float | None = None
    difference_pct: float | None = None
    confidence: str
    reasons: list[str] = Field(default_factory=list)


class DriverAnalysisOut(ApiModel):
    status: str
    window_days: int
    weeks: int
    samples: int
    drivers: list[DriverOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TrackingOverview(ApiModel):
    generated_at: datetime
    model_version: str
    days: int
    status: str
    accuracy: PredictionAccuracyOut
    drivers: DriverAnalysisOut
    goals: list[GoalTrackingOut] = Field(default_factory=list)
    actions: list[TrackedActionOut] = Field(default_factory=list)
    suggestions: list[ActionSuggestionOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Weekly briefing (M5)


class BriefingTrendOut(ApiModel):
    window_days: int
    as_of: date | None = None
    current_s: float | None = None
    previous_s: float | None = None
    change_s: float | None = None
    change_pct: float | None = None
    status: str


class BriefingDistanceOut(ApiModel):
    distance_key: str
    distance_m: float
    time_s: float | None = None
    low_s: float | None = None
    high_s: float | None = None
    goal_time_s: float | None = None
    goal_gap_s: float | None = None
    confidence: str


class BriefingSignalOut(ApiModel):
    key: str
    score: float | None = None
    status: str
    confidence: str
    reasons: list[str] = Field(default_factory=list)


class BriefingInsightOut(ApiModel):
    key: str
    dimension_key: str | None = None
    value: float | None = None
    reasons: list[str] = Field(default_factory=list)


class BriefingActionOut(ApiModel):
    dimension_key: str
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class BriefingView(ApiModel):
    generated_at: datetime
    model_version: str
    status: str
    as_of: date
    confidence: str
    confidence_score: float
    fitness_anchor: FitnessAnchorOut | None = None
    trends: list[BriefingTrendOut] = Field(default_factory=list)
    distances: list[BriefingDistanceOut] = Field(default_factory=list)
    signals: list[BriefingSignalOut] = Field(default_factory=list)
    headline: str
    headline_params: dict[str, float | int | str | None] = Field(default_factory=dict)
    improvement: BriefingInsightOut | None = None
    limitation: BriefingInsightOut | None = None
    action: BriefingActionOut | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Comparable pace–heart-rate analysis (M6)


class PaceHrPointOut(ApiModel):
    date: date
    activity_id: int
    activity_name: str
    avg_hr: int
    pace_s_per_km: float
    adjusted_pace_s_per_km: float | None = None
    distance_m: float
    elevation_gain_m: float | None = None
    period: str


class PaceHrLineOut(ApiModel):
    hr: float
    pace_s_per_km: float


class PaceHrGroupOut(ApiModel):
    key: str
    distance_band: str
    terrain_band: str
    sessions: int
    start: date
    end: date
    reference_hr: float
    hr_min: int
    hr_max: int
    early_pace_s_per_km: float | None = None
    recent_pace_s_per_km: float | None = None
    change_s_per_km: float | None = None
    change_pct: float | None = None
    status: str
    confidence: str
    confidence_score: float
    reasons: list[str] = Field(default_factory=list)
    points: list[PaceHrPointOut] = Field(default_factory=list)
    early_line: list[PaceHrLineOut] = Field(default_factory=list)
    recent_line: list[PaceHrLineOut] = Field(default_factory=list)


class PaceHrAnalysisOut(ApiModel):
    generated_at: datetime
    model_version: str
    window_days: int
    status: str
    sessions: int
    excluded_races: int
    excluded_hard: int
    excluded_missing_hr: int
    groups: list[PaceHrGroupOut] = Field(default_factory=list)
    primary_group: str | None = None
    conclusion: str
    conclusion_params: dict[str, float | int | str | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Recovery context from the Garmin export (M9)


class RecoveryMetricPointOut(ApiModel):
    date: date
    value: float


class RecoveryMetricOut(ApiModel):
    key: str
    unit: str
    latest_value: float | None = None
    latest_date: date | None = None
    avg_7d: float | None = None
    avg_28d: float | None = None
    change_28d: float | None = None
    change_28d_pct: float | None = None
    samples: int = 0
    coverage_days: int = 0
    points: list[RecoveryMetricPointOut] = Field(default_factory=list)


class RecoveryOverview(ApiModel):
    generated_at: datetime
    model_version: str
    days: int
    status: str
    imported_at: datetime | None = None
    metrics: list[RecoveryMetricOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
    kind: str = "file_import"
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    message: str | None = None
    metrics_imported: int = 0
    metrics_skipped: int = 0
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
