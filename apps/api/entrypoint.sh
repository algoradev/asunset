#!/bin/sh
# Runs Alembic migrations, then execs whatever command compose passed in.
# Migrations are idempotent (alembic tracks applied revisions), so this
# is safe to run on every container start.

set -eu

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] exec $@"
exec "$@"
