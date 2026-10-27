#!/usr/bin/env sh
set -eu

# Platforms with a release step migrate there; running it on every boot
# makes machines that start together race on the same DDL.
if [ "${RUN_MIGRATIONS_ON_START:-1}" = "1" ]; then
  alembic upgrade head
fi
exec uvicorn api.server:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers
