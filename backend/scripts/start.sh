#!/bin/sh
# Container entry point: migrate (and seed when SEED_ON_START=true), then serve.
set -eu
cd "$(dirname "$0")/.."
if [ "${SEED_ON_START:-true}" = "true" ]; then
  sh scripts/migrate_and_seed.sh
else
  python -m alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
