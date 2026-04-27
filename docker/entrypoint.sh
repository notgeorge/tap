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

echo "==> Starting Django development server..."
exec uv run python manage.py runserver 0.0.0.0:8000
