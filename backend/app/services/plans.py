"""Registered training plans (M12).

A registered plan is user-owned data: unlike the reconstructed M10 suggestion,
it has real rows with dates, targets and decisions. This module owns every
write path and the small read helpers shared by the calendar and adherence
views.

Validation is intentionally strict:

* sessions must fall inside the plan date range;
* rest sessions cannot carry distance or duration targets;
* every non-rest session needs at least a distance or a duration;
* only one plan can be active, enforced by a partial unique index and by
  deactivating the previous plan inside the same transaction;
* a linked activity must exist, cannot be used twice and cannot satisfy a
  skipped session.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Activity, PlannedRace, RaceGoal, TrainingPlan, TrainingPlanSession
from app.schemas_plans import (
    TrainingPlanCreate,
    TrainingPlanDetailOut,
    TrainingPlanFromSuggested,
    TrainingPlanOut,
    TrainingPlanSessionCreate,
    TrainingPlanSessionOut,
    TrainingPlanSessionUpdate,
    TrainingPlanUpdate,
    is_running_type,
)
from app.services.analysis import (
    build_sessions,
    select_phase,
    target_weekly_distance,
    week_start,
)
from app.utils import as_utc, utcnow


class PlanValidationError(Exception):
    """The request is well-formed but conflicts with the plan rules."""


class PlanConflictError(Exception):
    """The request conflicts with the current plan state."""


def _local_today(now: datetime | None = None, tz_offset_minutes: int = 0) -> date:
    reference = now or utcnow()
    return (as_utc(reference) + timedelta(minutes=tz_offset_minutes)).date()


def get_plan(db: Session, plan_id: int) -> TrainingPlan | None:
    return db.get(TrainingPlan, plan_id)


def get_active_plan(db: Session) -> TrainingPlan | None:
    return db.scalar(
        select(TrainingPlan)
        .where(
            TrainingPlan.is_active.is_(True),
            TrainingPlan.archived_at.is_(None),
        )
        .order_by(TrainingPlan.id)
    )


def plan_covers_week(plan: TrainingPlan, monday: date) -> bool:
    return plan.start_date <= monday + timedelta(days=6) and plan.end_date >= monday


def plan_sessions_in_range(
    plan: TrainingPlan,
    start: date,
    end: date,
) -> list[TrainingPlanSession]:
    return [session for session in plan.sessions if start <= session.session_date <= end]


def _activity_name(session: TrainingPlanSession) -> str | None:
    if session.activity is None:
        return None
    return session.activity.name


def session_out(session: TrainingPlanSession) -> TrainingPlanSessionOut:
    return TrainingPlanSessionOut(
        id=session.id,
        plan_id=session.plan_id,
        session_date=session.session_date,
        position=session.position,
        type=session.type,
        intensity=session.intensity,
        distance_m=round(session.distance_m, 1) if session.distance_m is not None else None,
        duration_s=round(session.duration_s, 1) if session.duration_s is not None else None,
        status=session.status,
        activity_id=session.activity_id,
        activity_name=_activity_name(session),
        notes=session.notes,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _plan_counts(sessions: list[TrainingPlanSession]) -> dict[str, float | int]:
    running = [session for session in sessions if is_running_type(session.type)]
    non_rest = [session for session in sessions if session.type != "rest"]
    return {
        "sessions_total": len(non_rest),
        "sessions_completed": len(
            [session for session in non_rest if session.status == "completed"]
        ),
        "sessions_skipped": len([session for session in non_rest if session.status == "skipped"]),
        "planned_distance_m": round(
            sum(float(session.distance_m or 0.0) for session in running), 1
        ),
        "planned_duration_s": round(
            sum(float(session.duration_s or 0.0) for session in running), 1
        ),
    }


def plan_out(plan: TrainingPlan, *, include_sessions: bool = False) -> TrainingPlanOut:
    counts = _plan_counts(list(plan.sessions))
    base = {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "goal_race_id": plan.goal_race_id,
        "goal_race_name": plan.goal_race.name if plan.goal_race is not None else None,
        "is_active": plan.is_active,
        "version": plan.version,
        "parent_plan_id": plan.parent_plan_id,
        "archived_at": plan.archived_at,
        "source": plan.source,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        **counts,
    }
    if include_sessions:
        return TrainingPlanDetailOut(
            **base,
            sessions=[
                session_out(session)
                for session in sorted(
                    plan.sessions,
                    key=lambda item: (item.session_date, item.position, item.id),
                )
            ],
        )
    return TrainingPlanOut(**base)


def list_plans(db: Session, include_archived: bool = False) -> list[TrainingPlanOut]:
    query = select(TrainingPlan).order_by(
        TrainingPlan.is_active.desc(),
        TrainingPlan.start_date.desc(),
        TrainingPlan.id.desc(),
    )
    if not include_archived:
        query = query.where(TrainingPlan.archived_at.is_(None))
    return [plan_out(plan) for plan in db.scalars(query).all()]


def _check_goal_race(db: Session, goal_race_id: int | None) -> None:
    if goal_race_id is not None and db.get(PlannedRace, goal_race_id) is None:
        raise PlanValidationError("Goal race not found")


def _check_dates(start: date, end: date) -> None:
    if end < start:
        raise PlanValidationError("end_date must be on or after start_date")


def _check_session_date(plan: TrainingPlan, session_date: date) -> None:
    if not (plan.start_date <= session_date <= plan.end_date):
        raise PlanValidationError("Session date must fall inside the plan range")


def create_plan(db: Session, payload: TrainingPlanCreate) -> TrainingPlan:
    _check_goal_race(db, payload.goal_race_id)
    plan = TrainingPlan(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        goal_race_id=payload.goal_race_id,
        source=payload.source,
        is_active=False,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(db: Session, plan_id: int, payload: TrainingPlanUpdate) -> TrainingPlan | None:
    plan = get_plan(db, plan_id)
    if plan is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        plan.name = data["name"].strip()
    if "description" in data:
        plan.description = data["description"].strip() if data["description"] else None
    if "start_date" in data and data["start_date"] is not None:
        plan.start_date = data["start_date"]
    if "end_date" in data and data["end_date"] is not None:
        plan.end_date = data["end_date"]
    if "goal_race_id" in data:
        _check_goal_race(db, data["goal_race_id"])
        plan.goal_race_id = data["goal_race_id"]
    _check_dates(plan.start_date, plan.end_date)
    for session in plan.sessions:
        _check_session_date(plan, session.session_date)
    plan.version += 1
    db.commit()
    db.refresh(plan)
    return plan


def delete_plan(db: Session, plan_id: int) -> bool:
    plan = get_plan(db, plan_id)
    if plan is None:
        return False
    db.delete(plan)
    db.commit()
    return True


def activate_plan(db: Session, plan_id: int) -> tuple[TrainingPlan, int | None]:
    plan = get_plan(db, plan_id)
    if plan is None:
        raise LookupError("Plan not found")
    if plan.archived_at is not None:
        raise PlanConflictError("Archived plans cannot be activated")
    if not plan.sessions:
        raise PlanConflictError("A plan needs at least one session before activation")
    previous = get_active_plan(db)
    replaced = previous.id if previous is not None and previous.id != plan.id else None
    if previous is not None and previous.id != plan.id:
        db.execute(
            update(TrainingPlan)
            .where(TrainingPlan.id == previous.id)
            .values(is_active=False, updated_at=utcnow())
        )
        db.flush()
    plan.is_active = True
    plan.archived_at = None
    plan.updated_at = utcnow()
    db.commit()
    db.refresh(plan)
    return plan, replaced


def archive_plan(db: Session, plan_id: int) -> TrainingPlan | None:
    plan = get_plan(db, plan_id)
    if plan is None:
        return None
    plan.is_active = False
    plan.archived_at = utcnow()
    plan.updated_at = utcnow()
    db.commit()
    db.refresh(plan)
    return plan


def _next_position(db: Session, plan_id: int) -> int:
    value = db.scalar(
        select(func.max(TrainingPlanSession.position)).where(TrainingPlanSession.plan_id == plan_id)
    )
    return int(value or 0) + 1


def _validate_session_values(
    type_: str,
    intensity: str,
    distance_m: float | None,
    duration_s: float | None,
) -> None:
    if type_ == "rest":
        if intensity != "rest":
            raise PlanValidationError("Rest sessions must use the rest intensity")
        if distance_m is not None or duration_s is not None:
            raise PlanValidationError("Rest sessions cannot have distance or duration targets")
        return
    if intensity == "rest":
        raise PlanValidationError("Only rest sessions can use the rest intensity")
    if distance_m is None and duration_s is None:
        raise PlanValidationError("Non-rest sessions need a distance or duration target")


def create_session(
    db: Session,
    plan: TrainingPlan,
    payload: TrainingPlanSessionCreate,
) -> TrainingPlanSession:
    _check_session_date(plan, payload.session_date)
    _validate_session_values(
        payload.type, payload.intensity, payload.distance_m, payload.duration_s
    )
    session = TrainingPlanSession(
        plan_id=plan.id,
        session_date=payload.session_date,
        position=payload.position if payload.position is not None else _next_position(db, plan.id),
        type=payload.type,
        intensity=payload.intensity,
        distance_m=payload.distance_m,
        duration_s=payload.duration_s,
        status=payload.status,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.refresh(plan)
    return session


def bulk_create_sessions(
    db: Session,
    plan: TrainingPlan,
    payloads: list[TrainingPlanSessionCreate],
) -> list[TrainingPlanSession]:
    """Create 1–400 sessions atomically.

    Every payload is validated before anything is added to the session, so a
    bad row leaves the plan untouched.
    """

    if not 1 <= len(payloads) <= 400:
        raise PlanValidationError("Bulk create accepts between 1 and 400 sessions")
    for payload in payloads:
        _check_session_date(plan, payload.session_date)
        _validate_session_values(
            payload.type, payload.intensity, payload.distance_m, payload.duration_s
        )
    position = _next_position(db, plan.id)
    sessions: list[TrainingPlanSession] = []
    for index, payload in enumerate(payloads):
        sessions.append(
            TrainingPlanSession(
                plan_id=plan.id,
                session_date=payload.session_date,
                position=(payload.position if payload.position is not None else position + index),
                type=payload.type,
                intensity=payload.intensity,
                distance_m=payload.distance_m,
                duration_s=payload.duration_s,
                status=payload.status,
                notes=payload.notes.strip() if payload.notes else None,
            )
        )
    db.add_all(sessions)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for session in sessions:
        db.refresh(session)
    db.refresh(plan)
    return sessions


def update_session(
    db: Session,
    plan: TrainingPlan,
    session: TrainingPlanSession,
    payload: TrainingPlanSessionUpdate,
) -> TrainingPlanSession:
    data = payload.model_dump(exclude_unset=True)
    if "session_date" in data and data["session_date"] is not None:
        _check_session_date(plan, data["session_date"])
        session.session_date = data["session_date"]
    if "position" in data and data["position"] is not None:
        session.position = data["position"]
    if "type" in data and data["type"] is not None:
        session.type = data["type"]
    if "intensity" in data and data["intensity"] is not None:
        session.intensity = data["intensity"]
    if "distance_m" in data:
        session.distance_m = data["distance_m"]
    if "duration_s" in data:
        session.duration_s = data["duration_s"]
    if "status" in data and data["status"] is not None:
        session.status = data["status"]
    if "notes" in data:
        session.notes = data["notes"].strip() if data["notes"] else None

    _check_session_date(plan, session.session_date)
    _validate_session_values(
        session.type, session.intensity, session.distance_m, session.duration_s
    )
    if session.status == "skipped" and session.activity_id is not None:
        raise PlanValidationError("Skipped sessions cannot keep a linked activity")
    db.commit()
    db.refresh(session)
    db.refresh(plan)
    return session


def delete_session(db: Session, plan: TrainingPlan, session: TrainingPlanSession) -> None:
    db.delete(session)
    db.commit()
    db.refresh(plan)


def _linked_elsewhere(
    db: Session,
    activity_id: int,
    *,
    session_id: int | None = None,
) -> TrainingPlanSession | None:
    query = select(TrainingPlanSession).where(TrainingPlanSession.activity_id == activity_id)
    if session_id is not None:
        query = query.where(TrainingPlanSession.id != session_id)
    return db.scalar(query)


def link_activity(
    db: Session,
    session: TrainingPlanSession,
    activity_id: int,
) -> TrainingPlanSession:
    if session.type == "rest":
        raise PlanValidationError("Rest sessions cannot link an activity")
    if session.status == "skipped":
        raise PlanValidationError("Skipped sessions cannot link an activity")
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise LookupError("Activity not found")
    if _linked_elsewhere(db, activity_id, session_id=session.id) is not None:
        raise PlanConflictError("That activity is already linked to another session")
    session.activity_id = activity_id
    session.status = "completed"
    db.commit()
    db.refresh(session)
    db.refresh(session.plan)
    return session


def unlink_activity(db: Session, session: TrainingPlanSession) -> TrainingPlanSession:
    if session.activity_id is None:
        return session
    session.activity_id = None
    if session.status == "completed":
        session.status = "planned"
    db.commit()
    db.refresh(session)
    db.refresh(session.plan)
    return session


def _recent_weekly_distance(db: Session, today: date) -> float:
    start = today - timedelta(days=27)
    total = db.scalar(
        select(func.coalesce(func.sum(Activity.distance_m), 0.0)).where(
            Activity.sport == "running",
            Activity.start_time_utc >= datetime(start.year, start.month, start.day),
            Activity.start_time_utc
            < datetime(today.year, today.month, today.day) + timedelta(days=1),
        )
    )
    return round(float(total or 0.0) / 4.0, 1)


def create_plan_from_suggested(
    db: Session,
    payload: TrainingPlanFromSuggested,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> TrainingPlan:
    """Materialise the current suggested plan as a registered plan.

    The reconstruction uses the same phase and volume rules as the M10
    adherence view, so the resulting plan is a faithful snapshot that the
    athlete can edit from then on. It is a convenience, not a second model.
    """

    from app.services.performance import build_overview

    _check_goal_race(db, payload.goal_race_id)
    today = _local_today(now, tz_offset_minutes)
    first_monday = week_start(payload.start_date or today)
    last_day = first_monday + timedelta(weeks=payload.weeks) - timedelta(days=1)

    goal = db.get(PlannedRace, payload.goal_race_id) if payload.goal_race_id else None
    goal_date = goal.race_date if goal is not None else None
    if goal is None:
        race_goal = db.scalar(
            select(RaceGoal).where(RaceGoal.target_date.is_not(None)).order_by(RaceGoal.target_date)
        )
        goal_date = race_goal.target_date if race_goal is not None else None

    overview = build_overview(db, now or utcnow())
    threshold = overview.fitness_anchor.pace_s_per_km if overview.fitness_anchor else None
    goal_pace = (
        goal.goal_time_s / (goal.distance_m / 1000.0)
        if goal is not None and goal.goal_time_s and goal.distance_m > 0
        else None
    )
    base_weekly = _recent_weekly_distance(db, today)

    plan = TrainingPlan(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        start_date=first_monday,
        end_date=last_day,
        goal_race_id=payload.goal_race_id,
        source="suggested",
        is_active=False,
    )
    db.add(plan)
    db.flush()

    sessions: list[TrainingPlanSession] = []
    for week_index in range(payload.weeks):
        monday = first_monday + timedelta(weeks=week_index)
        phase = select_phase(monday, goal_date, None)
        weekly_low, weekly_high = target_weekly_distance(phase.key, base_weekly)
        specs = build_sessions(
            phase.key,
            weekly_low,
            weekly_high,
            threshold,
            goal_pace,
            avoid_quality=phase.key == "recovery",
        )
        for day_index, spec in enumerate(specs):
            distance = None
            if spec.distance_low_m is not None and spec.distance_high_m is not None:
                distance = round((spec.distance_low_m + spec.distance_high_m) / 2.0, 1)
            duration = None
            if spec.duration_low_s is not None and spec.duration_high_s is not None:
                duration = round((spec.duration_low_s + spec.duration_high_s) / 2.0, 1)
            sessions.append(
                TrainingPlanSession(
                    plan_id=plan.id,
                    session_date=monday + timedelta(days=day_index),
                    position=week_index * 10 + day_index,
                    type=spec.type,
                    intensity=spec.intensity,
                    distance_m=distance,
                    duration_s=duration,
                    status="planned",
                )
            )
    db.add_all(sessions)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    if payload.activate and sessions:
        plan, _replaced = activate_plan(db, plan.id)
    return plan
