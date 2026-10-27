"""Run Dashboard API and SPA host."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from app.api import (
    activities,
    adherence,
    analysis,
    audit,
    auth,
    backups,
    briefing,
    comparables,
    imports,
    performance,
    progress,
    recovery,
    summary,
    sync,
    system,
    tracking,
)
from app.auth import require_auth
from app.config import configure_logging, get_settings
from app.db import get_session_factory
from app.models import IngestRun
from app.schemas import HealthResponse
from app.services.garmin import GarminError
from app.services.sync import scheduler
from app.utils import utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings.ensure_dirs()
    try:
        with get_session_factory()() as db:
            db.execute(
                update(IngestRun)
                .where(IngestRun.status == "running")
                .values(
                    status="interrupted",
                    finished_at=utcnow(),
                    message="Interrupted by application restart",
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - DB may not be migrated yet
        logger.warning("Could not clean up interrupted runs: %s", exc)

    if settings.auth_mode == "none":
        logger.info(
            "Authentication disabled. Bind the container to 127.0.0.1 or put it behind "
            "Tailscale/a reverse proxy."
        )
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Run Dashboard API",
    version=settings.app_version,
    description="Self-hosted running dashboard built on Garmin data.",
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(GarminError)
async def garmin_error_handler(_request, exc: GarminError):  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version)


app.include_router(auth.router, prefix="/api/v1")

api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])
api.include_router(activities.router)
api.include_router(backups.router)
api.include_router(summary.router)
api.include_router(audit.router)
api.include_router(analysis.router)
api.include_router(performance.router)
api.include_router(sync.router)
api.include_router(imports.router)
api.include_router(system.router)
api.include_router(progress.router)
api.include_router(tracking.router)
api.include_router(adherence.router)
api.include_router(recovery.router)
api.include_router(comparables.router)
api.include_router(briefing.router)
app.include_router(api)


def _static_dir() -> Path | None:
    candidate = settings.static_dir or (Path(__file__).parent / "static")
    if candidate.exists() and (candidate / "index.html").exists():
        return candidate
    return None


_static = _static_dir()
if _static is not None:
    assets = _static / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "docs", "redoc")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_static / full_path).resolve()
        root = _static.resolve()
        if full_path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_static / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "api": "/api/v1/health",
            "docs": "/docs",
            "frontend": "not built; run `bun run build` in frontend/",
        }
