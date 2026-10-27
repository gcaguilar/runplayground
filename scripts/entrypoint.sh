#!/bin/sh
# Apply a staged restore (if any), migrate the database, then hand over to the
# application process. The restore step runs before Alembic on purpose: the
# replacement database is at the revision recorded in its backup manifest.
set -eu

: "${DATA_DIR:=/data}"
export DATA_DIR

mkdir -p "$DATA_DIR"

cd /app
python -m app.cli apply-restore
alembic upgrade head

exec "$@"
