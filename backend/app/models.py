"""SQLAlchemy models.

The canonical ``activities`` row is source-independent. ``activity_sources``
records every place an activity came from (Garmin sync, manual upload), which
gives us provenance and cross-source deduplication without duplicating the
activity itself.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import utcnow


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sport: Mapped[str] = mapped_column(String(40), default="other", nullable=False, index=True)
    sub_sport: Mapped[str | None] = mapped_column(String(60))

    start_time_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    distance_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    moving_s: Mapped[float | None] = mapped_column(Float)
    elapsed_s: Mapped[float | None] = mapped_column(Float)

    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)
    avg_cadence_spm: Mapped[float | None] = mapped_column(Float)
    max_cadence_spm: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    max_speed_mps: Mapped[float | None] = mapped_column(Float)
    avg_power_w: Mapped[float | None] = mapped_column(Float)
    max_power_w: Mapped[float | None] = mapped_column(Float)

    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    elevation_loss_m: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    training_effect: Mapped[float | None] = mapped_column(Float)
    training_load: Mapped[float | None] = mapped_column(Float)

    device_name: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(80))

    is_race: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_streams: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_gps: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_laps: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_flags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    sources: Mapped[list[ActivitySource]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", lazy="selectin"
    )
    streams: Mapped[list[StreamSample]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    laps: Mapped[list[ActivityLap]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="ActivityLap.lap_index",
        lazy="selectin",
    )
    best_efforts: Mapped[list[BestEffort]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_activities_start_sport", "start_time_utc", "sport"),)

    @property
    def avg_pace_s_per_km(self) -> float | None:
        if self.distance_m and self.distance_m > 0 and self.duration_s and self.duration_s > 0:
            return self.duration_s / (self.distance_m / 1000.0)
        return None

    @property
    def source_names(self) -> list[str]:
        return sorted({source.source for source in self.sources})

    @property
    def primary_source(self) -> str | None:
        if not self.sources:
            return None
        ordered = sorted(self.sources, key=lambda source: source.imported_at)
        return ordered[0].source

    @property
    def quality_flag_list(self) -> list[str]:
        flags = self.quality_flags or {}
        return list(flags.get("flags", []))


class ActivitySource(Base):
    __tablename__ = "activity_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    raw_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id", ondelete="SET NULL"))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(30))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="sources")
    raw_file: Mapped[RawFile | None] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_activity_source_external"),
    )


class RawFile(Base):
    __tablename__ = "raw_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="upload", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class StreamSample(Base):
    __tablename__ = "stream_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_utc: Mapped[datetime | None] = mapped_column(DateTime)
    elapsed_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    heart_rate: Mapped[int | None] = mapped_column(Integer)
    cadence_spm: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    power_w: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)

    activity: Mapped[Activity] = relationship(back_populates="streams")

    __table_args__ = (
        UniqueConstraint("activity_id", "sample_index", name="uq_stream_activity_index"),
        Index("ix_stream_activity_index", "activity_id", "sample_index"),
    )


class ActivityLap(Base):
    __tablename__ = "activity_laps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lap_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time_utc: Mapped[datetime | None] = mapped_column(DateTime)
    distance_m: Mapped[float | None] = mapped_column(Float)
    timer_s: Mapped[float | None] = mapped_column(Float)
    elapsed_s: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)
    avg_cadence_spm: Mapped[float | None] = mapped_column(Float)
    max_cadence_spm: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    max_speed_mps: Mapped[float | None] = mapped_column(Float)
    ascent_m: Mapped[float | None] = mapped_column(Float)
    descent_m: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)

    activity: Mapped[Activity] = relationship(back_populates="laps")

    __table_args__ = (UniqueConstraint("activity_id", "lap_index", name="uq_lap_activity_index"),)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    mode: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    activities_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activities_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activities_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activities_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_downloaded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class BestEffort(Base):
    """Fastest continuous segment of an activity at a standard race distance.

    The same activity can hold efforts at several distances (a 10K race also
    contains a 5K split). ``method`` records whether the effort uses the whole
    activity or a segment of its stream, so predictions can weigh a real race
    result differently from a split.
    """

    __tablename__ = "best_efforts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    segment_start_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    segment_end_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="stream", nullable=False)
    is_full_activity: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="best_efforts", lazy="joined")

    __table_args__ = (
        UniqueConstraint("activity_id", "distance_m", name="uq_best_effort_activity_distance"),
        Index("ix_best_efforts_distance_duration", "distance_m", "duration_s"),
    )


class RaceGoal(Base):
    """A target time for one of the standard distances.

    Goals are deliberately simple in M1: one active goal per distance. The
    calendar and multiple named races arrive in M3 without changing this table.
    """

    __tablename__ = "race_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    distance_m: Mapped[float] = mapped_column(Float, unique=True, nullable=False)
    target_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    race_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class PlannedRace(Base):
    """A race the athlete intends to run, with its own target and priority.

    ``race_goals`` remains the canonical goal per standard distance used by the
    prediction models. Planned races add the calendar view: several named
    events, A/B/C priorities and an optional link to the activity that
    eventually completes them.
    """

    __tablename__ = "planned_races"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    race_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    goal_time_s: Mapped[float | None] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(1), default="B", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class GoalRevision(Base):
    """One saved target for a standard distance, with the prediction in force.

    ``race_goals`` holds only the current target. Every time the target or its
    date changes we append a revision so the tracking view can show what was
    asked for and what the model predicted at that moment. Re-saving an
    identical target does not create noise.
    """

    __tablename__ = "goal_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    target_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    race_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    prediction_time_s: Mapped[float | None] = mapped_column(Float)
    prediction_low_s: Mapped[float | None] = mapped_column(Float)
    prediction_high_s: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_goal_revisions_distance_created", "distance_m", "created_at"),)


class TrackedAction(Base):
    """User status for one training recommendation.

    The recommendation itself is derived from diagnostics on every request;
    this table only stores the decision (pending, in progress, completed), a
    note and the baseline score captured when the athlete started tracking it.
    That baseline turns a generic suggestion into a hypothesis we can check
    later without claiming causality.
    """

    __tablename__ = "tracked_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimension_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    baseline_score: Mapped[float | None] = mapped_column(Float)
    baseline_confidence: Mapped[str | None] = mapped_column(String(20))
    baseline_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PerformanceSnapshot(Base):
    """One prediction set per day, used to draw the evolution over time."""

    __tablename__ = "performance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    model_version: Mapped[str] = mapped_column(String(30), nullable=False)
    fitness_anchor_s: Mapped[float | None] = mapped_column(Float)
    fitness_anchor_low_s: Mapped[float | None] = mapped_column(Float)
    fitness_anchor_high_s: Mapped[float | None] = mapped_column(Float)
    fitness_confidence: Mapped[str | None] = mapped_column(String(20))
    predictions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ExternalMetric(Base):
    """Historical metric imported from a Garmin data export.

    ``distance_m`` is 0 for non-distance metrics. Using 0 instead of NULL keeps
    the unique constraint effective in SQLite, where NULL values never collide.
    """

    __tablename__ = "external_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    distance_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(500))
    source_key: Mapped[str | None] = mapped_column(String(255))
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source",
            "metric",
            "metric_date",
            "distance_m",
            name="uq_external_metric_source_metric_date_distance",
        ),
        Index("ix_external_metrics_metric_date_lookup", "metric", "metric_date"),
    )
