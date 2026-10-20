#!/bin/sh
# Bring the schema up to date, then load sample data if the database is empty.
# Pass --reset to wipe all data and reseed (used to restore the review data set).
set -eu
cd "$(dirname "$0")/.."
python -m alembic upgrade head
python -m app.seed "$@"
