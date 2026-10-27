"""Persistent analysis thresholds and activity classification (M11).

The 10K fitness anchor is deliberately *not* configurable: predictions, race
potential and snapshots keep using the observed anchor. These settings only
calibrate how the app reads training intensity, load and the derived views
(diagnostics, plan, calendar, reports, adherence, tracking, comparable runs).

Manual values live in ``app_state`` under ``analysis_settings`` so no extra
table is needed. Observed values are read from the data on every request.
A threshold heart rate is never observed: it is either set by hand or reported
as missing, in which case HR classification keeps using max HR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, AppState, ExternalMetric
from app.schemas import (
    AnalysisSettingsOut,
    AnalysisSettingsUpdate,
    AnalysisSettingsValuesOut,
    PerformanceOverview,
)
from app.services.performance import build_overview
from app.utils import utcnow

ANALYSIS_SETTINGS_KEY = "analysis_settings"
CLASSIFICATION_MODES = ("auto", "pace", "hr")


@dataclass(frozen=True)
class ResolvedAnalysisSettings:
    """Effective thresholds plus their provenance."""

    response: AnalysisSettingsOut

    @property
    def manual(self) -> AnalysisSettingsValuesOut:
        return self.response.manual

    @property
    def observed(self) -> AnalysisSettingsValuesOut:
        return self.response.observed

    @property
    def effective(self) -> AnalysisSettingsValuesOut:
        return self.response.effective

    @property
    def mode(self) -> str:
        return self.effective.classification_mode or "auto"

    @property
    def max_hr(self) -> int | None:
        return self.effective.max_hr

    @property
    def resting_hr(self) -> int | None:
        return self.effective.resting_hr

    @property
    def threshold_hr(self) -> int | None:
        return self.effective.threshold_hr

    @property
    def threshold_pace_s_per_km(self) -> float | None:
        return self.effective.threshold_pace_s_per_km

    @property
    def hr_reference(self) -> float | None:
        """The value the HR cuts are relative to (threshold HR, else max HR)."""

        return self.effective.threshold_hr or self.effective.max_hr

    @property
    def has_manual(self) -> bool:
        return any(value is not None for value in self.manual.model_dump().values())


def get_analysis_settings(
    db: Session,
    now: datetime | None = None,
    overview: PerformanceOverview | None = None,
) -> ResolvedAnalysisSettings:
    """Resolve manual, observed and effective values without writing."""

    reference = now or utcnow()
    performance = overview or build_overview(db, reference)
    observed = _observed_values(db, performance)
    manual, updated_at = _stored_manual(db)
    effective = _effective_values(observed, manual)
    sources = _sources(observed, manual, effective)
    warnings = _warnings(observed, manual, effective)
    return ResolvedAnalysisSettings(
        response=AnalysisSettingsOut(
            observed=observed,
            manual=manual,
            effective=effective,
            sources=sources,
            warnings=warnings,
            updated_at=updated_at,
        )
    )


def put_analysis_settings(
    db: Session,
    payload: AnalysisSettingsUpdate,
    now: datetime | None = None,
) -> ResolvedAnalysisSettings:
    """Validate and persist the manual values, then resolve again."""

    reference = now or utcnow()
    data = payload.model_dump(exclude_unset=True)
    current, _updated_at = _stored_manual(db)
    overview = build_overview(db, reference)

    merged = current.model_dump()
    for key, value in data.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value

    try:
        validated = AnalysisSettingsUpdate.model_validate(merged)
    except ValidationError as exc:
        raise ValueError(_validation_message(exc)) from exc

    observed = _observed_values(db, overview)
    effective = _effective_values(observed, validated)
    _validate_effective(effective)

    stored = {key: value for key, value in validated.model_dump().items() if value is not None}
    row = db.get(AppState, ANALYSIS_SETTINGS_KEY)
    if row is None:
        db.add(AppState(key=ANALYSIS_SETTINGS_KEY, value=stored, updated_at=reference))
    else:
        row.value = stored
        row.updated_at = reference
    db.commit()

    return get_analysis_settings(db, reference, overview=overview)


def _stored_manual(db: Session) -> tuple[AnalysisSettingsValuesOut, datetime | None]:
    row = db.get(AppState, ANALYSIS_SETTINGS_KEY)
    if row is None:
        return AnalysisSettingsValuesOut(), None
    raw = row.value if isinstance(row.value, dict) else {}
    manual = _clean_values(raw)
    return manual, row.updated_at


def _clean_values(raw: dict) -> AnalysisSettingsValuesOut:
    """Tolerate hand-edited or legacy state instead of failing the page."""

    def integer(key: str, low: int, high: int) -> int | None:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        parsed = int(value)
        return parsed if low <= parsed <= high else None

    def number(key: str, low: float, high: float) -> float | None:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        parsed = float(value)
        return round(parsed, 1) if low <= parsed <= high else None

    mode = raw.get("classification_mode")
    return AnalysisSettingsValuesOut(
        max_hr=integer("max_hr", 100, 230),
        resting_hr=integer("resting_hr", 30, 120),
        threshold_hr=integer("threshold_hr", 100, 230),
        threshold_pace_s_per_km=number("threshold_pace_s_per_km", 120, 1200),
        classification_mode=mode if mode in CLASSIFICATION_MODES else None,  # type: ignore[arg-type]
    )


def _observed_values(db: Session, overview: PerformanceOverview) -> AnalysisSettingsValuesOut:
    anchor = overview.fitness_anchor
    max_hr = db.scalar(
        select(func.max(Activity.max_hr)).where(
            Activity.sport == "running",
            Activity.max_hr.is_not(None),
        )
    )
    resting_hr = db.scalar(
        select(ExternalMetric.value)
        .where(ExternalMetric.metric == "resting_hr")
        .order_by(ExternalMetric.metric_date.desc(), ExternalMetric.id.desc())
        .limit(1)
    )
    return AnalysisSettingsValuesOut(
        max_hr=int(max_hr) if max_hr is not None else None,
        resting_hr=round(float(resting_hr)) if resting_hr is not None else None,
        threshold_hr=None,
        threshold_pace_s_per_km=(round(anchor.pace_s_per_km, 1) if anchor is not None else None),
        classification_mode=None,
    )


def _effective_values(
    observed: AnalysisSettingsValuesOut,
    manual: AnalysisSettingsValuesOut,
) -> AnalysisSettingsValuesOut:
    max_hr = manual.max_hr if manual.max_hr is not None else observed.max_hr
    return AnalysisSettingsValuesOut(
        max_hr=max_hr,
        resting_hr=(manual.resting_hr if manual.resting_hr is not None else observed.resting_hr),
        threshold_hr=manual.threshold_hr,
        threshold_pace_s_per_km=(
            manual.threshold_pace_s_per_km
            if manual.threshold_pace_s_per_km is not None
            else observed.threshold_pace_s_per_km
        ),
        classification_mode=manual.classification_mode or "auto",
    )


def _sources(
    observed: AnalysisSettingsValuesOut,
    manual: AnalysisSettingsValuesOut,
    effective: AnalysisSettingsValuesOut,
) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key in ("max_hr", "resting_hr", "threshold_hr", "threshold_pace_s_per_km"):
        if getattr(manual, key) is not None:
            sources[key] = "manual"
        elif getattr(observed, key) is not None:
            sources[key] = "observed"
        elif getattr(effective, key) is not None:
            sources[key] = "derived"
        else:
            sources[key] = "missing"
    sources["classification_mode"] = (
        "manual" if manual.classification_mode is not None else "derived"
    )
    return sources


def _warnings(
    observed: AnalysisSettingsValuesOut,
    manual: AnalysisSettingsValuesOut,
    effective: AnalysisSettingsValuesOut,
) -> list[str]:
    warnings: list[str] = []
    if observed.max_hr is None:
        warnings.append("no_observed_max_hr")
    if observed.resting_hr is None:
        warnings.append("no_observed_resting_hr")
    if observed.threshold_pace_s_per_km is None:
        warnings.append("no_observed_threshold_pace")
    if effective.threshold_hr is None:
        warnings.append("no_threshold_hr")
    if effective.threshold_pace_s_per_km is None:
        warnings.append("no_threshold_pace")
    if manual.threshold_hr is not None and manual.max_hr is None:
        warnings.append("manual_threshold_without_manual_max_hr")
    return warnings


def _validate_effective(effective: AnalysisSettingsValuesOut) -> None:
    if (
        effective.max_hr is not None
        and effective.threshold_hr is not None
        and effective.threshold_hr > effective.max_hr
    ):
        raise ValueError("threshold_hr must be lower than or equal to max_hr")
    if (
        effective.resting_hr is not None
        and effective.threshold_hr is not None
        and effective.resting_hr >= effective.threshold_hr
    ):
        raise ValueError("resting_hr must be lower than threshold_hr")


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid analysis settings"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = str(first.get("msg", "Invalid value"))
    return f"{location}: {message}" if location else message
