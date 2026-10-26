# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------
FROM oven/bun:1.4.4-alpine AS frontend

WORKDIR /build

COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
RUN bun run build

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/app/static \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN pip install .

COPY --from=frontend /build/dist ./app/static
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint
RUN chmod 0755 /usr/local/bin/entrypoint \
    && groupadd --gid 1000 run \
    && useradd --uid 1000 --gid 1000 --home-dir /data \
       --no-create-home --shell /usr/sbin/nologin run \
    && mkdir -p /data \
    && chown run:run /data

USER run

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=4).status == 200 else 1)"

LABEL org.opencontainers.image.title="Run Dashboard" \
      org.opencontainers.image.description="Self-hosted running dashboard built on Garmin data" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENTRYPOINT ["entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
