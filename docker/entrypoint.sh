#!/bin/bash
# TAP Development Entrypoint Script
#
# Runs on container startup before the Django server. Handles:
# 1. Python dependency sync (idempotent; first start downloads, later starts no-op)
# 2. Database migrations
# 3. Django development server
#
# The dependency sync lives here (rather than in the Dockerfile) because
# /app/.venv and /root/.cache/uv are named volumes mounted at runtime —
# anything we install at build time is hidden at runtime. Doing it in the
# entrypoint means the install lands in the per-project container venv and
# uv cache volumes, which is what we actually want to use.
#
# Exit immediately if any command fails
set -e

echo "==> Syncing Python dependencies (uv sync)..."
uv sync

echo "==> Running database migrations..."
uv run python manage.py migrate --noinput

# Start the Huey consumer (tap_cares scheduler tick) as a background process.
# v0 deploys a single Huey worker (req-tap-cares-scheduler-huey-4). Running it
# alongside runserver keeps dev to a single container — when the container
# stops, the trap kills Huey too. Note: Huey does NOT auto-reload on file
# changes; restart the container if you edit scheduler or task code.
echo "==> Starting Huey consumer (scheduler tick)..."
uv run python manage.py run_huey -w 1 &
HUEY_PID=$!
trap "kill ${HUEY_PID} 2>/dev/null || true" EXIT

echo "==> Starting Django development server..."
exec uv run python manage.py runserver 0.0.0.0:8000
