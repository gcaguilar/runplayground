"""Small operational CLI.

Examples:
    python -m app.cli sync --mode incremental
    python -m app.cli create-db
    python -m app.cli export-openapi
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import configure_logging, get_settings
from app.db import create_all, get_session_factory
from app.models import IngestRun
from app.services.sync import run_garmin_sync
from app.utils import utcnow


def cmd_sync(mode: str) -> int:
    settings = get_settings()
    if not settings.garmin_configured:
        print("GARMIN_PERSONAL_API_KEY is not configured.", file=sys.stderr)
        return 2
    session = get_session_factory()()
    try:
        run = IngestRun(
            kind="garmin_sync",
            mode=mode,
            status="running",
            started_at=utcnow(),
            message="CLI sync",
        )
        session.add(run)
        session.commit()
        run_id = run.id
    finally:
        session.close()

    session = get_session_factory()()
    try:
        run_garmin_sync(session, run_id, mode)
        run = session.get(IngestRun, run_id)
        print(f"run {run_id}: {run.status} — {run.message}")
        if run and run.errors_count:
            for error in (run.details or {}).get("errors") or []:
                print(f"  - {error}", file=sys.stderr)
        return 0 if run and run.status in {"success", "partial"} else 1
    finally:
        session.close()


def cmd_create_db() -> int:
    create_all()
    print(f"Database ready at {get_settings().resolved_database_url}")
    return 0


def cmd_export_openapi() -> int:
    from app.main import app

    target = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {target}")
    return 0


def cmd_recompute() -> int:
    from app.services.performance import (
        build_overview,
        mark_efforts_refreshed,
        refresh_all_efforts,
        store_snapshot,
    )

    session = get_session_factory()()
    try:
        activities, efforts = refresh_all_efforts(session)
        mark_efforts_refreshed(session, activities, efforts)
        session.commit()
        overview = build_overview(session)
        store_snapshot(session, overview)
        anchor = overview.fitness_anchor
        print(f"activities: {activities}, efforts: {efforts}, status: {overview.status}")
        if anchor is not None:
            print(f"10K anchor: {anchor.time_s:.0f}s ({anchor.confidence})")
        return 0
    finally:
        session.close()


def cmd_check() -> int:
    settings = get_settings()
    print(f"app: {settings.app_name} {settings.app_version}")
    print(f"database: {settings.resolved_database_url}")
    print(f"data dir: {settings.data_dir.resolve()}")
    print(f"garmin configured: {settings.garmin_configured}")
    print(f"auth mode: {settings.auth_mode}")
    print(f"sync interval: {settings.sync_interval_hours}h")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="run-dashboard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="run a Garmin sync")
    sync_parser.add_argument("--mode", choices=["incremental", "backfill"], default="incremental")

    subparsers.add_parser("create-db", help="create tables without Alembic (development)")
    subparsers.add_parser("export-openapi", help="write frontend/openapi.json")
    subparsers.add_parser("recompute", help="rebuild best efforts and performance snapshots")
    subparsers.add_parser("check", help="print effective configuration")

    args = parser.parse_args()
    if args.command == "sync":
        return cmd_sync(args.mode)
    if args.command == "create-db":
        return cmd_create_db()
    if args.command == "export-openapi":
        return cmd_export_openapi()
    if args.command == "recompute":
        return cmd_recompute()
    if args.command == "check":
        return cmd_check()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
