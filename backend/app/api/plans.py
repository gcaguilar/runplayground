"""Registered training plan endpoints (M12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TrainingPlanSession
from app.schemas_plans import (
    TrainingPlanActivationOut,
    TrainingPlanBulkOut,
    TrainingPlanCreate,
    TrainingPlanDetailOut,
    TrainingPlanFromSuggested,
    TrainingPlanLinkActivity,
    TrainingPlanOut,
    TrainingPlanSessionCreate,
    TrainingPlanSessionOut,
    TrainingPlanSessionsBulk,
    TrainingPlanSessionUpdate,
    TrainingPlanUpdate,
)
from app.services import plans as service

router = APIRouter(prefix="/training-plans", tags=["training-plans"])


def _plan(db: Session, plan_id: int):
    plan = service.get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


def _session(db: Session, plan_id: int, session_id: int) -> TrainingPlanSession:
    session = db.get(TrainingPlanSession, session_id)
    if session is None or session.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, service.PlanConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, service.PlanValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


@router.get("", response_model=list[TrainingPlanOut])
def list_plans(
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[TrainingPlanOut]:
    return service.list_plans(db, include_archived=include_archived)


@router.post("", response_model=TrainingPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(payload: TrainingPlanCreate, db: Session = Depends(get_db)) -> TrainingPlanOut:
    try:
        plan = service.create_plan(db, payload)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return service.plan_out(plan)


@router.post(
    "/from-suggested",
    response_model=TrainingPlanDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_from_suggested(
    payload: TrainingPlanFromSuggested,
    tz_offset_minutes: int = Query(0, ge=-14 * 60, le=14 * 60),
    db: Session = Depends(get_db),
) -> TrainingPlanDetailOut:
    try:
        plan = service.create_plan_from_suggested(db, payload, tz_offset_minutes=tz_offset_minutes)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return service.plan_out(plan, include_sessions=True)


@router.get("/{plan_id}", response_model=TrainingPlanDetailOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)) -> TrainingPlanDetailOut:
    plan = _plan(db, plan_id)
    return service.plan_out(plan, include_sessions=True)


@router.patch("/{plan_id}", response_model=TrainingPlanDetailOut)
def patch_plan(
    plan_id: int,
    payload: TrainingPlanUpdate,
    db: Session = Depends(get_db),
) -> TrainingPlanDetailOut:
    try:
        plan = service.update_plan(db, plan_id, payload)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return service.plan_out(plan, include_sessions=True)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, db: Session = Depends(get_db)) -> Response:
    if not service.delete_plan(db, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{plan_id}/activate", response_model=TrainingPlanActivationOut)
def activate_plan(plan_id: int, db: Session = Depends(get_db)) -> TrainingPlanActivationOut:
    try:
        plan, replaced = service.activate_plan(db, plan_id)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return TrainingPlanActivationOut(
        plan_id=plan.id,
        is_active=plan.is_active,
        replaced_plan_id=replaced,
    )


@router.post("/{plan_id}/archive", response_model=TrainingPlanOut)
def archive_plan(plan_id: int, db: Session = Depends(get_db)) -> TrainingPlanOut:
    plan = service.archive_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return service.plan_out(plan)


@router.post(
    "/{plan_id}/sessions",
    response_model=TrainingPlanSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    plan_id: int,
    payload: TrainingPlanSessionCreate,
    db: Session = Depends(get_db),
) -> TrainingPlanSessionOut:
    plan = _plan(db, plan_id)
    try:
        session = service.create_session(db, plan, payload)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return service.session_out(session)


@router.post(
    "/{plan_id}/sessions/bulk",
    response_model=TrainingPlanBulkOut,
    status_code=status.HTTP_201_CREATED,
)
def bulk_create_sessions(
    plan_id: int,
    payload: TrainingPlanSessionsBulk,
    db: Session = Depends(get_db),
) -> TrainingPlanBulkOut:
    plan = _plan(db, plan_id)
    try:
        sessions = service.bulk_create_sessions(db, plan, payload.sessions)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return TrainingPlanBulkOut(
        created=len(sessions),
        sessions=[service.session_out(session) for session in sessions],
    )


@router.patch(
    "/{plan_id}/sessions/{session_id}",
    response_model=TrainingPlanSessionOut,
)
def patch_session(
    plan_id: int,
    session_id: int,
    payload: TrainingPlanSessionUpdate,
    db: Session = Depends(get_db),
) -> TrainingPlanSessionOut:
    plan = _plan(db, plan_id)
    session = _session(db, plan_id, session_id)
    try:
        session = service.update_session(db, plan, session, payload)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return service.session_out(session)


@router.delete(
    "/{plan_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(plan_id: int, session_id: int, db: Session = Depends(get_db)) -> Response:
    plan = _plan(db, plan_id)
    session = _session(db, plan_id, session_id)
    service.delete_session(db, plan, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{plan_id}/sessions/{session_id}/activity",
    response_model=TrainingPlanSessionOut,
)
def link_activity(
    plan_id: int,
    session_id: int,
    payload: TrainingPlanLinkActivity,
    db: Session = Depends(get_db),
) -> TrainingPlanSessionOut:
    _plan(db, plan_id)
    session = _session(db, plan_id, session_id)
    try:
        session = service.link_activity(db, session, payload.activity_id)
    except Exception as exc:  # noqa: BLE001 - translated to HTTP below
        raise _translate(exc) from exc
    return service.session_out(session)


@router.delete(
    "/{plan_id}/sessions/{session_id}/activity",
    response_model=TrainingPlanSessionOut,
)
def unlink_activity(
    plan_id: int, session_id: int, db: Session = Depends(get_db)
) -> TrainingPlanSessionOut:
    _plan(db, plan_id)
    session = _session(db, plan_id, session_id)
    session = service.unlink_activity(db, session)
    return service.session_out(session)
