"""Small key/value helpers for non-secret application state."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AppState
from app.utils import utcnow


def get_state(db: Session, key: str, default: dict | None = None) -> dict:
    row = db.get(AppState, key)
    return row.value if row else (default or {})


def set_state(db: Session, key: str, value: dict) -> None:
    row = db.get(AppState, key)
    if row is None:
        db.add(AppState(key=key, value=value, updated_at=utcnow()))
    else:
        row.value = value
        row.updated_at = utcnow()
