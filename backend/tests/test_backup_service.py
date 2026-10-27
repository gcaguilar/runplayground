from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base
from app.models import Activity, RawFile
from app.services.backup import (
    apply_pending_restore,
    create_backup,
    pending_restore,
    stage_pending_restore,
)


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / 'run.db'}",
        max_backup_mb=64,
        max_restore_mb=64,
        auth_mode="none",
    )


def _activity(name: str) -> Activity:
    return Activity(
        fingerprint=f"fingerprint-{name}",
        name=name,
        sport="running",
        start_time_utc=datetime(2026, 5, 30, 7, 0, tzinfo=UTC).replace(tzinfo=None),
        distance_m=5000,
        duration_s=1800,
    )


def test_apply_pending_restore_keeps_pre_restore_backup_and_replaces_data(tmp_path):
    settings = _settings(tmp_path)
    settings.ensure_dirs()
    engine = create_engine(settings.resolved_database_url)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    raw_data = b"FIT-like bytes"
    raw_path = settings.raw_dir / "ab" / "abc.fit"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(raw_data)
    session.add(
        RawFile(
            sha256="a" * 64,
            filename="original.fit",
            content_type="application/vnd.garmin.fit",
            size_bytes=len(raw_data),
            storage_path="raw/ab/abc.fit",
            source="upload",
        )
    )
    session.add(_activity("before"))
    session.commit()

    backup = create_backup(settings, session)
    assert backup.path.is_file()
    session.close()
    engine.dispose()

    # Change the live data in a way the restore should undo.
    engine = create_engine(settings.resolved_database_url)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.execute(Activity.__table__.delete())
    session.add(_activity("after"))
    session.commit()
    session.close()
    engine.dispose()
    raw_path.write_bytes(b"changed")

    pending = stage_pending_restore(backup.path, "my-backup.zip", settings)
    assert pending.original_filename == "my-backup.zip"
    assert pending_restore(settings) is not None
    result = apply_pending_restore(settings)
    assert result.applied is True
    assert result.pre_restore_database is not None
    assert result.pre_restore_database.is_file()
    assert result.pre_restore_database.name.startswith("run.db.pre-restore-")
    assert pending_restore(settings) is None
    assert not settings.restore_pending_dir.exists()

    engine = create_engine(settings.resolved_database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        names = session.scalars(select(Activity.name)).all()
        assert names == ["before"]
        assert session.scalar(select(func.count(Activity.id))) == 1
    finally:
        session.close()
    engine.dispose()
    assert raw_path.read_bytes() == raw_data

    marker = json.loads(settings.restore_marker_path.read_text())
    assert marker["status"] == "applied"
    assert marker["manifest"]["counts"]["activities"] == 1
    assert marker["original_filename"] == "my-backup.zip"

    pre_engine = create_engine(f"sqlite:///{result.pre_restore_database}")
    with pre_engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM activities").scalar()
        assert count == 1
        name = connection.exec_driver_sql("SELECT name FROM activities").scalar()
        assert name == "after"
    pre_engine.dispose()

    shutil.rmtree(backup.path.parent, ignore_errors=True)


def test_apply_pending_restore_without_pending_is_a_noop(tmp_path):
    settings = _settings(tmp_path)
    settings.ensure_dirs()
    result = apply_pending_restore(settings)
    assert result.applied is False
    assert "No pending" in result.message
