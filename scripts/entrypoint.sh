#!/bin/sh
# Apply database migrations, then hand over to the application process.
set -eu

: "${DATA_DIR:=/data}"
export DATA_DIR

mkdir -p "$DATA_DIR"

cd /app
alembic upgrade head

exec "$@"
