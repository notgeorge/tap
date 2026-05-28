# TAP Development Dockerfile
# Base image: Official Python 3.14 slim variant (smaller than full image, has what we need)
FROM python:3.14-slim

# ============================================================================
# Environment Variables
# ============================================================================

# Prevents Python from writing .pyc bytecode files to disk
# In containers these waste space and can cause stale cache issues
ENV PYTHONDONTWRITEBYTECODE=1

# Forces Python stdout/stderr to be unbuffered
# Without this, logs may not appear immediately in 'docker compose logs'
ENV PYTHONUNBUFFERED=1

# UV normally uses hardlinks for installed packages to save disk space
# In Docker, hardlinks between layers cause issues, so we tell UV to copy instead
ENV UV_LINK_MODE=copy

# ============================================================================
# System Setup
# ============================================================================

# Set the working directory inside the container
# All subsequent commands run from this directory
WORKDIR /app

# Install system-level dependencies
# - postgresql-client: needed for Django to talk to PostgreSQL (pg_isready, psql)
# - curl: used by the tailwindcss binary install below; also handy for shell
#   debugging from inside the container
# - --no-install-recommends: skip optional packages to keep image small
# - rm -rf /var/lib/apt/lists/*: clean up apt cache to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# UV Package Manager
# ============================================================================

# Copy UV binary from the official UV container image
# UV is a fast Python package manager written in Rust (replaces pip)
# This is the recommended way to install UV in Docker
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ============================================================================
# Dependencies
# ============================================================================
#
# Dependency installation runs at container START via docker/entrypoint.sh,
# NOT at image build. The reasons:
#
#   1. The compose bind mount `.:/app` overrides /app at runtime, so any
#      /app/.venv populated at build time is hidden anyway — pure waste.
#   2. /root/.cache/uv is a named volume (compose), so a build-time uv sync
#      can't pre-populate it usefully either.
#   3. Crucially, baking uv's cache into an image layer means Docker's build
#      cache can fossilize a corrupted uv state and replay it across every
#      rebuild. Moving the sync to runtime (with a named-volume cache) keeps
#      cache state mutable per-session and reset-able by `dc down -v`.
#
# We still copy the lock + pyproject so the image carries them, but we don't
# install. First container start does `uv sync` and populates the worktree's
# .venv plus the named-volume cache.

COPY pyproject.toml uv.lock* ./

# ============================================================================
# Application Code
# ============================================================================

# Copy the rest of the application code into the container
# This layer changes frequently, so it comes after dependencies
COPY . .

# Note on tailwindcss:
# The image does NOT carry the tailwindcss binary. It's installed on demand
# by the /tailwind-rebuild skill (tap_web/skills/tailwind-rebuild/SKILL.md)
# into the `tailwind_bin` named volume mounted at /opt/tailwind. The
# compiled stylesheet at tap_web/static/tap_web/css/tailwind.css is
# committed to source — production serves the committed artifact; dev
# regenerates it via the skill before committing template changes that
# touch utility classes. See tap_web/specs/spec-web-tailwind-pipeline.md.

# ============================================================================
# Runtime Configuration
# ============================================================================

# Document that the container listens on port 8000
# This is informational - you still need to map the port in docker-compose
EXPOSE 8000

# Copy the entrypoint script and make it executable
# The entrypoint handles: migrations, conditional seed data, then server start
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default command to run when the container starts
# The entrypoint script runs migrations, seeds data (if DEBUG), then starts Django
CMD ["/entrypoint.sh"]
