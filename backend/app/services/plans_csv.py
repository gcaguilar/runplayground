"""CSV import and export for registered training plans (M19).

The format is deliberately small and stable:

* UTF-8 text with an optional BOM and a mandatory header row;
* ISO dates (``YYYY-MM-DD``), dot decimals and metric units in the file
  (kilometres and minutes, or metres and seconds through explicit columns);
* one row per session, in any order.

Import is atomic: every row is parsed and validated before the plan and its
sessions are added to the database. A dry run returns the same normalized rows
plus line-numbered errors and never writes. The validation reuses the CRUD
rules from :mod:`app.services.plans`, so a CSV cannot create a session that a
manual write would reject.
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import TrainingPlan, TrainingPlanSession
from app.schemas_plans import (
    SessionIntensity,
    SessionStatus,
    SessionType,
    TrainingPlanCsvIssueOut,
    TrainingPlanCsvPreviewOut,
    TrainingPlanCsvRowOut,
)
from app.services.plans import get_active_plan
from app.utils import utcnow

EXPORT_COLUMNS = (
    "session_date",
    "type",
    "intensity",
    "distance_km",
    "duration_min",
    "status",
    "notes",
)
MAX_CSV_ROWS = 400
MAX_CSV_BYTES = 1024 * 1024
MAX_NAME_LENGTH = 255
MAX_NOTES_LENGTH = 2000

# Canonical field -> accepted header names. Matching is case-insensitive and
# ignores surrounding whitespace. Unknown columns are ignored on purpose so a
# spreadsheet can carry extra notes without breaking the import.
HEADER_ALIASES: dict[str, frozenset[str]] = {
    "session_date": frozenset({"session_date", "date", "fecha"}),
    "type": frozenset({"type", "tipo"}),
    "intensity": frozenset({"intensity", "intensidad"}),
    "distance_km": frozenset({"distance_km", "distance", "distancia_km"}),
    "distance_m": frozenset({"distance_m", "distancia_m"}),
    "duration_min": frozenset({"duration_min", "duration", "duracion_min"}),
    "duration_s": frozenset({"duration_s", "duracion_s"}),
    "status": frozenset({"status", "estado"}),
    "notes": frozenset({"notes", "notas"}),
}
REQUIRED_FIELDS = ("session_date", "type", "intensity")
SESSION_TYPES = frozenset(SessionType.__args__)
SESSION_INTENSITIES = frozenset(SessionIntensity.__args__)
SESSION_STATUSES = frozenset(SessionStatus.__args__)


@dataclass(frozen=True)
class CsvIssue:
    line: int
    message: str

    def as_out(self) -> TrainingPlanCsvIssueOut:
        return TrainingPlanCsvIssueOut(line=self.line, message=self.message)

    def label(self) -> str:
        return f"Line {self.line}: {self.message}" if self.line > 0 else self.message


@dataclass
class CsvParseResult:
    plan_name: str
    rows: list[TrainingPlanCsvRowOut] = field(default_factory=list)
    errors: list[CsvIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and bool(self.rows)

    @property
    def start_date(self) -> date | None:
        return min((row.session_date for row in self.rows), default=None)

    @property
    def end_date(self) -> date | None:
        return max((row.session_date for row in self.rows), default=None)

    def preview(self, message: str | None = None) -> TrainingPlanCsvPreviewOut:
        return TrainingPlanCsvPreviewOut(
            valid=self.valid,
            message=message,
            plan_name=self.plan_name,
            start_date=self.start_date,
            end_date=self.end_date,
            row_count=len(self.rows),
            rows=self.rows,
            errors=[issue.as_out() for issue in self.errors],
        )


class PlanCsvImportError(Exception):
    """The CSV is well-formed but at least one row or header is invalid."""

    def __init__(self, result: CsvParseResult):
        super().__init__("; ".join(issue.label() for issue in result.errors))
        self.result = result


class PlanCsvTooLargeError(Exception):
    """The uploaded file exceeds the fixed CSV size limit."""


def plan_csv_bytes(plan: TrainingPlan) -> bytes:
    """Serialise every session of a plan with the stable M19 header."""

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for session in sorted(
        plan.sessions,
        key=lambda item: (item.session_date, item.position, item.id),
    ):
        writer.writerow(
            [
                session.session_date.isoformat(),
                session.type,
                session.intensity,
                _number(session.distance_m / 1000.0 if session.distance_m is not None else None),
                _number(session.duration_s / 60.0 if session.duration_s is not None else None),
                session.status,
                session.notes or "",
            ]
        )
    return buffer.getvalue().encode("utf-8")


def plan_csv_filename(plan: TrainingPlan, now: datetime | None = None) -> str:
    """A safe, ASCII-only export name with the plan slug and a timestamp."""

    stamp = (now or utcnow()).strftime("%Y%m%d-%H%M%S")
    slug = _ascii_slug(plan.name) or "plan"
    return f"plan-{slug[:60]}-{stamp}.csv"


def parse_plan_csv(content: bytes, filename: str | None, name: str | None = None) -> CsvParseResult:
    """Parse and validate a CSV payload without touching the database."""

    plan_name = _plan_name(name, filename)
    result = CsvParseResult(plan_name=plan_name)
    if not content.strip():
        result.errors.append(CsvIssue(0, "The CSV file is empty"))
        return result
    if not plan_name:
        result.errors.append(CsvIssue(0, "The plan name cannot be empty"))
    elif len(plan_name) > MAX_NAME_LENGTH:
        result.errors.append(
            CsvIssue(0, f"The plan name must be at most {MAX_NAME_LENGTH} characters")
        )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        result.errors.append(CsvIssue(0, "The CSV file must be encoded as UTF-8"))
        return result

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        raw_header = next(reader)
    except StopIteration:
        result.errors.append(CsvIssue(0, "The CSV file is empty"))
        return result

    header_line = reader.line_num or 1
    field_by_index = _map_header(raw_header, header_line, result.errors)
    if not field_by_index:
        return result

    data_rows = 0
    for values in reader:
        line = reader.line_num
        if not any(value.strip() for value in values):
            continue
        if len(values) != len(raw_header):
            result.errors.append(
                CsvIssue(
                    line,
                    f"Expected {len(raw_header)} columns but found {len(values)}",
                )
            )
            continue
        data_rows += 1
        if data_rows > MAX_CSV_ROWS:
            result.errors.append(
                CsvIssue(line, f"A plan CSV accepts at most {MAX_CSV_ROWS} session rows")
            )
            break
        row, issues = _parse_row(values, field_by_index, line, data_rows)
        result.errors.extend(issues)
        if row is not None:
            result.rows.append(row)

    if data_rows == 0:
        result.errors.append(CsvIssue(header_line, "The CSV has no session rows"))
    return result


def import_plan_csv(
    db: Session,
    result: CsvParseResult,
    *,
    activate: bool = False,
) -> TrainingPlan:
    """Create the plan and all its sessions from a parsed payload.

    Validation happens before this function; here the whole write is one
    transaction, including the optional activation and the deactivation of the
    previous plan.
    """

    if not result.valid:
        raise PlanCsvImportError(result)
    plan = TrainingPlan(
        name=result.plan_name,
        description=None,
        start_date=result.start_date,
        end_date=result.end_date,
        source="import",
        is_active=False,
    )
    db.add(plan)
    try:
        db.flush()
        db.add_all(
            [
                TrainingPlanSession(
                    plan_id=plan.id,
                    session_date=row.session_date,
                    position=row.position,
                    type=row.type,
                    intensity=row.intensity,
                    distance_m=row.distance_m,
                    duration_s=row.duration_s,
                    status=row.status,
                    notes=row.notes,
                )
                for row in result.rows
            ]
        )
        if activate:
            previous = get_active_plan(db)
            if previous is not None:
                db.execute(
                    update(TrainingPlan)
                    .where(TrainingPlan.id == previous.id)
                    .values(is_active=False, updated_at=utcnow())
                )
                db.flush()
            plan.is_active = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    return plan


def _map_header(
    raw_header: list[str],
    line: int,
    errors: list[CsvIssue],
) -> dict[int, str]:
    mapping: dict[int, str] = {}
    seen: dict[str, int] = {}
    for index, raw in enumerate(raw_header):
        header = raw.strip().lower()
        if not header:
            continue
        canonical = next(
            (field for field, aliases in HEADER_ALIASES.items() if header in aliases),
            None,
        )
        if canonical is None:
            continue
        if canonical in seen:
            message = (
                f"Column {raw.strip()!r} duplicates {canonical!r} on column {seen[canonical] + 1}"
            )
            errors.append(CsvIssue(line, message))
            continue
        seen[canonical] = index
        mapping[index] = canonical
    present = set(mapping.values())
    missing = [field for field in REQUIRED_FIELDS if field not in present]
    if missing:
        errors.append(CsvIssue(line, f"Missing required column(s): {', '.join(missing)}"))
    return mapping


def _parse_row(
    values: list[str],
    mapping: dict[int, str],
    line: int,
    position: int,
) -> tuple[TrainingPlanCsvRowOut | None, list[CsvIssue]]:
    cells = {field: values[index].strip() for index, field in mapping.items()}
    errors: list[CsvIssue] = []

    raw_date = cells.get("session_date", "")
    session_date: date | None = None
    if not raw_date:
        errors.append(CsvIssue(line, "session_date is required"))
    else:
        try:
            session_date = date.fromisoformat(raw_date)
        except ValueError:
            errors.append(CsvIssue(line, f"Invalid session_date {raw_date!r}; expected YYYY-MM-DD"))

    type_ = cells.get("type", "").lower()
    if not type_:
        errors.append(CsvIssue(line, "type is required"))
    elif type_ not in SESSION_TYPES:
        errors.append(
            CsvIssue(
                line,
                f"Invalid type {type_!r}; expected one of {', '.join(sorted(SESSION_TYPES))}",
            )
        )

    intensity = cells.get("intensity", "").lower()
    if not intensity:
        errors.append(CsvIssue(line, "intensity is required"))
    elif intensity not in SESSION_INTENSITIES:
        errors.append(
            CsvIssue(
                line,
                f"Invalid intensity {intensity!r}; expected one of "
                f"{', '.join(sorted(SESSION_INTENSITIES))}",
            )
        )

    status = cells.get("status", "").lower() or "planned"
    if status not in SESSION_STATUSES:
        errors.append(
            CsvIssue(
                line,
                f"Invalid status {status!r}; expected one of {', '.join(sorted(SESSION_STATUSES))}",
            )
        )

    distance_values = {
        field: cells.get(field, "")
        for field in ("distance_km", "distance_m")
        if cells.get(field, "")
    }
    duration_values = {
        field: cells.get(field, "")
        for field in ("duration_min", "duration_s")
        if cells.get(field, "")
    }
    if len(distance_values) > 1:
        errors.append(CsvIssue(line, "Use exactly one of distance_km or distance_m"))
    if len(duration_values) > 1:
        errors.append(CsvIssue(line, "Use exactly one of duration_min or duration_s"))

    distance_m = _read_distance(distance_values, line, errors)
    duration_s = _read_duration(duration_values, line, errors)

    notes = cells.get("notes") or None
    if notes is not None and len(notes) > MAX_NOTES_LENGTH:
        errors.append(CsvIssue(line, f"notes must be at most {MAX_NOTES_LENGTH} characters"))

    if type_ in SESSION_TYPES and intensity in SESSION_INTENSITIES:
        if type_ == "rest":
            if intensity != "rest":
                errors.append(CsvIssue(line, "Rest sessions must use the rest intensity"))
            if distance_m is not None or duration_s is not None:
                errors.append(
                    CsvIssue(line, "Rest sessions cannot have distance or duration targets")
                )
        else:
            if intensity == "rest":
                errors.append(CsvIssue(line, "Only rest sessions can use the rest intensity"))
            if distance_m is None and duration_s is None:
                errors.append(
                    CsvIssue(line, "Non-rest sessions need a distance or duration target")
                )

    if session_date is None or errors:
        return None, errors
    return (
        TrainingPlanCsvRowOut(
            line=line,
            position=position,
            session_date=session_date,
            type=type_,
            intensity=intensity,
            distance_m=distance_m,
            duration_s=duration_s,
            status=status,
            notes=notes,
        ),
        errors,
    )


def _read_distance(
    values: dict[str, str],
    line: int,
    errors: list[CsvIssue],
) -> float | None:
    if not values:
        return None
    field, raw = next(iter(values.items()))
    value = _read_number(raw, field, line, errors)
    if value is None:
        return None
    metres = value * 1000.0 if field == "distance_km" else value
    if metres > 500_000:
        errors.append(CsvIssue(line, "distance must be at most 500 km (500000 m)"))
        return None
    return round(metres, 1)


def _read_duration(
    values: dict[str, str],
    line: int,
    errors: list[CsvIssue],
) -> float | None:
    if not values:
        return None
    field, raw = next(iter(values.items()))
    value = _read_number(raw, field, line, errors)
    if value is None:
        return None
    seconds = value * 60.0 if field == "duration_min" else value
    if seconds > 24 * 3600:
        errors.append(CsvIssue(line, "duration must be at most 24 hours (86400 s)"))
        return None
    return round(seconds, 1)


def _read_number(
    raw: str,
    field: str,
    line: int,
    errors: list[CsvIssue],
) -> float | None:
    try:
        value = float(raw)
    except ValueError:
        errors.append(CsvIssue(line, f"{field} must be a number, got {raw!r}"))
        return None
    if not math.isfinite(value):
        errors.append(CsvIssue(line, f"{field} must be a finite number"))
        return None
    if value <= 0:
        errors.append(CsvIssue(line, f"{field} must be positive"))
        return None
    return value


def _plan_name(name: str | None, filename: str | None) -> str:
    if name is not None and name.strip():
        return name.strip()
    if filename:
        stem = Path(filename).name
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        return stem.strip() or "Imported plan"
    return "Imported plan"


def _number(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _ascii_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


__all__ = [
    "CsvIssue",
    "CsvParseResult",
    "EXPORT_COLUMNS",
    "MAX_CSV_BYTES",
    "MAX_CSV_ROWS",
    "PlanCsvImportError",
    "PlanCsvTooLargeError",
    "import_plan_csv",
    "parse_plan_csv",
    "plan_csv_bytes",
    "plan_csv_filename",
]
