"""Background Garmin sync orchestration.

A sync runs in a daemon thread so the HTTP request that starts it returns
immediately. Progress is persisted in ``ingest_runs`` and the UI polls the
status endpoint. The scheduler only triggers one sync at a time.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import zipfile
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session_factory
from app.models import Activity, ActivitySource, IngestRun
from app.parsers import ParseError
from app.parsers.fit import parse_fit
from app.services.garmin import GarminApiError, GarminAuthError, GarminClient, GarminError
from app.services.garmin_mapping import merge_fit_with_garmin, parsed_from_garmin
from app.services.ingest import ingest_garmin
from app.services.performance import build_overview, ensure_efforts, store_snapshot
from app.services.state import set_state
from app.utils import fingerprint, utcnow

logger = logging.getLogger(__name__)


class SyncManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.running = False
        self.current_run_id: int | None = None
        self.current_mode: str | None = None

    def start(self, mode: str = "incremental") -> tuple[bool, int | None, str]:
        if mode not in {"incremental", "backfill"}:
            return False, None, "Unknown sync mode"

        with self._lock:
            if self.running:
                return False, self.current_run_id, "A sync is already running"
            settings = get_settings()
            if not settings.garmin_configured:
                return False, None, "GARMIN_PERSONAL_API_KEY is not configured"

            session = get_session_factory()()
            try:
                run = IngestRun(
                    kind="garmin_sync",
                    mode=mode,
                    status="running",
                    started_at=utcnow(),
                    message="Starting sync",
                )
                session.add(run)
                session.commit()
                run_id = run.id
            finally:
                session.close()

            self.running = True
            self.current_run_id = run_id
            self.current_mode = mode
            self._thread = threading.Thread(
                target=self._worker,
                args=(run_id, mode),
                name=f"garmin-sync-{run_id}",
                daemon=True,
            )
            self._thread.start()
            return True, run_id, "Sync started"

    def _worker(self, run_id: int, mode: str) -> None:
        session = get_session_factory()()
        try:
            run_garmin_sync(session, run_id, mode)
        except Exception as exc:  # noqa: BLE001 - background boundary
            logger.exception("Garmin sync failed")
            _fail_run(session, run_id, str(exc))
        finally:
            session.close()
            with self._lock:
                self.running = False
                self._thread = None
                self.current_run_id = None
                self.current_mode = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "current_run_id": self.current_run_id,
                "mode": self.current_mode,
            }


manager = SyncManager()


def run_garmin_sync(db: Session, run_id: int, mode: str) -> None:
    settings = get_settings()
    run = db.get(IngestRun, run_id)
    if run is None:
        return

    errors: list[str] = []
    created = 0
    updated = 0
    skipped = 0
    seen = 0
    files_downloaded = 0

    try:
        with GarminClient(settings) as client:
            client.auth.get_token()
            max_pages = (
                settings.sync_incremental_max_pages
                if mode == "incremental"
                else settings.sync_backfill_max_pages
            )
            page_size = 50

            for page in range(max_pages):
                items = client.get_activities(start=page * page_size, limit=page_size)
                if not items:
                    break

                work_in_page = 0
                for summary in items:
                    seen += 1
                    try:
                        work = _process_activity(db, client, summary, settings)
                        if work is None:
                            skipped += 1
                            continue
                        status, _activity_id, downloaded = work
                        if status == "imported":
                            created += 1
                            work_in_page += 1
                        elif status == "merged":
                            updated += 1
                            work_in_page += 1
                        else:
                            skipped += 1
                        if downloaded:
                            files_downloaded += 1
                    except (GarminApiError, GarminError, ParseError) as exc:
                        db.rollback()
                        errors.append(f"{summary.get('activityId')}: {exc}")
                        logger.warning("Could not ingest Garmin activity: %s", exc)
                    except Exception as exc:  # noqa: BLE001 - keep the sync alive
                        db.rollback()
                        errors.append(f"{summary.get('activityId')}: {exc}")
                        logger.exception("Unexpected error ingesting Garmin activity")

                    run.activities_seen = seen
                    run.activities_created = created
                    run.activities_updated = updated
                    run.activities_skipped = skipped
                    run.files_downloaded = files_downloaded
                    run.errors_count = len(errors)
                    run.message = f"Page {page + 1}: {len(items)} activities"
                    db.commit()

                if mode == "incremental" and work_in_page == 0:
                    break

        status = "success" if not errors else "partial"
        message = (
            f"{created} new, {updated} merged, {skipped} skipped"
            if not errors
            else f"{created} new, {updated} merged, {skipped} skipped, {len(errors)} errors"
        )
        run.status = status
        run.message = message
        run.finished_at = utcnow()
        run.details = {"errors": errors[:50]}
        set_state(
            db,
            "sync",
            {
                "last_run_id": run.id,
                "last_finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "last_status": status,
                "last_mode": mode,
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "errors": len(errors),
            },
        )
        db.commit()
        # A sync is the most natural moment to close the day's prediction
        # snapshot, even if nobody opens the dashboard. Failure here must not
        # turn a successful sync into an error.
        try:
            ensure_efforts(db)
            store_snapshot(db, build_overview(db))
        except Exception as exc:  # noqa: BLE001 - snapshot is best effort
            db.rollback()
            logger.warning("Could not store performance snapshot after sync: %s", exc)
        logger.info("Garmin sync finished: %s", message)
    except (GarminAuthError, GarminError) as exc:
        _fail_run(db, run_id, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        _fail_run(db, run_id, f"Unexpected sync failure: {exc}")
        raise


def _process_activity(
    db: Session,
    client: GarminClient,
    summary: dict[str, Any],
    settings: Settings,
) -> tuple[str, int | None, bool] | None:
    activity_id = summary.get("activityId")
    if activity_id is None:
        raise ParseError("Garmin activity has no id")

    source = db.scalar(
        select(ActivitySource).where(
            ActivitySource.source == "garmin_api",
            ActivitySource.external_id == str(activity_id),
        )
    )
    existing = db.get(Activity, source.activity_id) if source else None
    if existing is not None and existing.has_streams:
        return None

    # An activity imported manually may already match this Garmin activity.
    preliminary = parsed_from_garmin(summary)
    fp = fingerprint(preliminary.sport, preliminary.start_time_utc, preliminary.distance_m)
    matched = db.scalar(select(Activity).where(Activity.fingerprint == fp))
    has_streams_already = bool(matched and matched.has_streams)

    detail: dict[str, Any] = {}
    if source is None or not has_streams_already:
        detail = client.get_activity(activity_id)
        _sleep(settings)

    parsed = parsed_from_garmin(summary, detail)
    fit_bytes: bytes | None = None
    warning: str | None = None

    if settings.sync_download_fit and not has_streams_already:
        try:
            archive = client.download_activity_file(activity_id)
            fit_bytes = extract_fit(archive)
            fit_activity = parse_fit(fit_bytes)
            parsed = merge_fit_with_garmin(fit_activity, parsed)
        except (GarminApiError, GarminError) as exc:
            warning = f"fit_download_failed:{exc}"
            logger.warning("Could not download FIT for %s: %s", activity_id, exc)
        except ParseError as exc:
            warning = f"fit_parse_failed:{exc}"
            logger.warning("Could not parse FIT for %s: %s", activity_id, exc)
        _sleep(settings)

    outcome = ingest_garmin(db, parsed, activity_id, fit_bytes, warning=warning)
    return outcome.status, outcome.activity_id, fit_bytes is not None


def extract_fit(payload: bytes) -> bytes:
    if payload[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                candidates = [name for name in archive.namelist() if name.lower().endswith(".fit")]
                if not candidates:
                    raise ParseError("Garmin archive contains no FIT file")
                candidates.sort(key=lambda name: archive.getinfo(name).file_size, reverse=True)
                return archive.read(candidates[0])
        except zipfile.BadZipFile as exc:
            raise ParseError(f"Invalid Garmin ZIP archive: {exc}") from exc
    if len(payload) >= 12 and payload[8:12] == b".FIT":
        return payload
    raise ParseError("Garmin download is neither a ZIP nor a FIT file")


def _fail_run(db: Session, run_id: int, message: str) -> None:
    run = db.get(IngestRun, run_id)
    if run is None:
        return
    run.status = "error"
    run.message = message[:1000]
    run.finished_at = utcnow()
    run.errors_count = max(run.errors_count, 1)
    set_state(
        db,
        "sync",
        {
            "last_run_id": run.id,
            "last_finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "last_status": "error",
            "last_mode": run.mode,
            "errors": 1,
        },
    )
    db.commit()


class SyncScheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        settings = get_settings()
        if settings.sync_interval_hours <= 0 and not settings.sync_on_startup:
            return
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="garmin-scheduler", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        settings = get_settings()
        if settings.sync_on_startup and settings.garmin_configured:
            if self._stop.wait(5):
                return
            manager.start("incremental")
        if settings.sync_interval_hours <= 0:
            return
        interval = max(settings.sync_interval_hours, 1) * 3600
        while not self._stop.wait(interval):
            if settings.garmin_configured:
                manager.start("incremental")

    def stop(self) -> None:
        self._stop.set()


scheduler = SyncScheduler()


def _sleep(settings: Settings) -> None:
    if settings.sync_request_delay_seconds > 0:
        time.sleep(settings.sync_request_delay_seconds)


def stale_sync_threshold(settings: Settings) -> timedelta:
    return timedelta(hours=max(settings.sync_interval_hours * 2, 24))
