#!/bin/sh
# Runs Alembic migrations (platform + product via combined version_locations),
# then execs the compose-passed command.

set -eu

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] exec $@"
exec "$@"
