#!/bin/bash
# TAP Development Entrypoint Script
#
# Runs on container startup before the Django server. Handles:
# 1. Python dependency sync (idempotent; first start downloads, later starts no-op)
# 2. Database migrations
# 3. Django development server
#
# The dependency sync lives here (rather than in the Dockerfile) because both
# /app/.venv and /root/.cache/uv are mounted at runtime — anything we install
# at build time is hidden at runtime. Doing it in the entrypoint means the
# install lands in the bind-mounted worktree and the named-volume cache, which
# is what we actually want to use.
#
# Exit immediately if any command fails
set -e

echo "==> Syncing Python dependencies (uv sync)..."
uv sync

echo "==> Running database migrations..."
uv run python manage.py migrate --noinput

# Start the Huey consumer (tap_cares scheduler tick) as a background process.
# Being phased out — see spec-tap-cares-task-backend.md
# req-tap-cares-task-backend-huey-removal. The next migration commit replaces
# this with the Steady Queue @recurring scheduler tick.
echo "==> Starting Huey consumer (scheduler tick)..."
uv run python manage.py run_huey -w 1 &
HUEY_PID=$!

# Start the Steady Queue supervisor as a background process. It forks one
# worker process per Configuration.Worker in settings.STEADY_QUEUE — one for
# the scheduler queue, one for the default queue — giving OS-level isolation
# between the once-per-minute clock and collector execution
# (req-tap-cares-task-backend-queue-isolation, req-tap-cares-task-backend-
# deployment-1). Same in-container pattern Huey uses; trap kills it on exit.
# Steady Queue does NOT auto-reload; restart the container if you edit task
# code (req-tap-cares-task-backend-deployment-3).
echo "==> Starting Steady Queue supervisor..."
uv run python manage.py steady_queue &
STEADY_QUEUE_PID=$!

trap "kill ${HUEY_PID} ${STEADY_QUEUE_PID} 2>/dev/null || true" EXIT

echo "==> Starting Django development server..."
exec uv run python manage.py runserver 0.0.0.0:8000
