#!/bin/bash
# TAP Development Entrypoint Script
#
# Runs on container startup before the Django server. Handles:
# 1. Database migrations (always)
# 2. Seed data (only when DEBUG=true)
# 3. Django development server
#
# Exit immediately if any command fails
set -e

echo "==> Running database migrations..."
uv run python manage.py migrate --noinput

echo "==> Starting Django development server..."
exec uv run python manage.py runserver 0.0.0.0:8000
