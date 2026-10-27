"""API contracts for registered training plans (M12).

Plans are user-owned data, so their contracts live in a dedicated module to
keep ``schemas.py`` focused on derived views. Calendar and adherence only need
small summaries; those stay in ``schemas.py`` so the shared contracts do not
depend on this module.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas import ApiModel

PlanSource = Literal["manual", "suggested", "import"]
SessionType = Literal[
    "rest",
    "easy",
    "recovery",
    "strides",
    "long",
    "threshold",
    "race_pace",
    "strength",
    "cross_training",
    "other",
]
SessionIntensity = Literal["rest", "easy", "moderate", "hard"]
SessionStatus = Literal["planned", "completed", "skipped"]

RUNNING_SESSION_TYPES = frozenset(
    {"easy", "recovery", "strides", "long", "threshold", "race_pace", "other"}
)
REST_SESSION_TYPES = frozenset({"rest"})
NON_RUNNING_SESSION_TYPES = frozenset({"strength", "cross_training"})
DISTANCE_SESSION_TYPES = RUNNING_SESSION_TYPES


def is_running_type(type_: str) -> bool:
    return type_ in DISTANCE_SESSION_TYPES


def _check_goals(
    type_: str,
    intensity: str,
    distance_m: float | None,
    duration_s: float | None,
) -> None:
    if type_ == "rest":
        if intensity != "rest":
            raise ValueError("rest sessions must use the rest intensity")
        if distance_m is not None or duration_s is not None:
            raise ValueError("rest sessions cannot have distance or duration targets")
        return
    if intensity == "rest":
        raise ValueError("only rest sessions can use the rest intensity")
    if distance_m is None and duration_s is None:
        raise ValueError("non-rest sessions need a distance or duration target")
    if distance_m is not None and distance_m <= 0:
        raise ValueError("distance_m must be positive")
    if duration_s is not None and duration_s <= 0:
        raise ValueError("duration_s must be positive")


class TrainingPlanCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date
    end_date: date
    goal_race_id: int | None = Field(default=None, ge=1)
    source: PlanSource = "manual"

    @model_validator(mode="after")
    def _dates(self) -> TrainingPlanCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TrainingPlanUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    goal_race_id: int | None = Field(default=None, ge=1)


class TrainingPlanFromSuggested(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    weeks: Literal[4, 8, 12] = 4
    goal_race_id: int | None = Field(default=None, ge=1)
    activate: bool = False


class TrainingPlanSessionCreate(ApiModel):
    session_date: date
    position: int | None = Field(default=None, ge=0)
    type: SessionType
    intensity: SessionIntensity = "easy"
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    duration_s: float | None = Field(default=None, gt=0, le=24 * 3600)
    status: SessionStatus = "planned"
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _goals(self) -> TrainingPlanSessionCreate:
        _check_goals(self.type, self.intensity, self.distance_m, self.duration_s)
        return self


class TrainingPlanSessionUpdate(ApiModel):
    session_date: date | None = None
    position: int | None = Field(default=None, ge=0)
    type: SessionType | None = None
    intensity: SessionIntensity | None = None
    distance_m: float | None = Field(default=None, gt=0, le=500_000)
    duration_s: float | None = Field(default=None, gt=0, le=24 * 3600)
    status: SessionStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TrainingPlanSessionsBulk(ApiModel):
    sessions: list[TrainingPlanSessionCreate] = Field(min_length=1, max_length=400)


class TrainingPlanLinkActivity(ApiModel):
    activity_id: int = Field(ge=1)


class TrainingPlanSessionOut(ApiModel):
    id: int
    plan_id: int
    session_date: date
    position: int
    type: str
    intensity: str
    distance_m: float | None = None
    duration_s: float | None = None
    status: str
    activity_id: int | None = None
    activity_name: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TrainingPlanOut(ApiModel):
    id: int
    name: str
    description: str | None = None
    start_date: date
    end_date: date
    goal_race_id: int | None = None
    goal_race_name: str | None = None
    is_active: bool
    version: int
    parent_plan_id: int | None = None
    archived_at: datetime | None = None
    source: str
    created_at: datetime
    updated_at: datetime
    sessions_total: int = 0
    sessions_completed: int = 0
    sessions_skipped: int = 0
    planned_distance_m: float = 0.0
    planned_duration_s: float = 0.0


class TrainingPlanDetailOut(TrainingPlanOut):
    sessions: list[TrainingPlanSessionOut] = Field(default_factory=list)


class TrainingPlanActivationOut(ApiModel):
    plan_id: int
    is_active: bool
    replaced_plan_id: int | None = None


class TrainingPlanDeleteOut(ApiModel):
    deleted: bool
    id: int


class TrainingPlanBulkOut(ApiModel):
    created: int
    sessions: list[TrainingPlanSessionOut] = Field(default_factory=list)


class TrainingPlanCsvIssueOut(ApiModel):
    """One CSV problem, always tied to a physical line of the uploaded file."""

    line: int
    message: str


class TrainingPlanCsvRowOut(ApiModel):
    """One normalized session parsed from a CSV row (metres and seconds)."""

    line: int
    position: int
    session_date: date
    type: str
    intensity: str
    distance_m: float | None = None
    duration_s: float | None = None
    status: str
    notes: str | None = None


class TrainingPlanCsvPreviewOut(ApiModel):
    """Dry-run result for a plan CSV upload.

    ``valid`` is false when the payload cannot be imported; ``rows`` still
    contains every row that parsed correctly so the UI can show what would be
    created. Nothing is written in a dry run.
    """

    valid: bool
    message: str | None = None
    plan_name: str
    start_date: date | None = None
    end_date: date | None = None
    row_count: int = 0
    rows: list[TrainingPlanCsvRowOut] = Field(default_factory=list)
    errors: list[TrainingPlanCsvIssueOut] = Field(default_factory=list)


__all__ = [
    "NON_RUNNING_SESSION_TYPES",
    "REST_SESSION_TYPES",
    "RUNNING_SESSION_TYPES",
    "SessionIntensity",
    "SessionStatus",
    "SessionType",
    "TrainingPlanActivationOut",
    "TrainingPlanBulkOut",
    "TrainingPlanCreate",
    "TrainingPlanCsvRowOut",
    "TrainingPlanCsvPreviewOut",
    "TrainingPlanCsvIssueOut",
    "TrainingPlanDeleteOut",
    "TrainingPlanDetailOut",
    "TrainingPlanFromSuggested",
    "TrainingPlanLinkActivity",
    "TrainingPlanOut",
    "TrainingPlanSessionCreate",
    "TrainingPlanSessionOut",
    "TrainingPlanSessionUpdate",
    "TrainingPlanSessionsBulk",
    "TrainingPlanUpdate",
    "is_running_type",
]
