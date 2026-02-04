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
# - --no-install-recommends: skip optional packages to keep image small
# - rm -rf /var/lib/apt/lists/*: clean up apt cache to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
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

# Copy dependency files first, before the rest of the code
# Docker caches each layer - if pyproject.toml hasn't changed,
# Docker reuses the cached dependency layer (much faster rebuilds)
COPY pyproject.toml uv.lock* ./

# Install Python dependencies using UV
# --frozen: use exact versions from uv.lock (reproducible builds)
# The fallback (|| uv sync) handles first run when no lock file exists yet
RUN uv sync --frozen --no-dev || uv sync

# ============================================================================
# Application Code
# ============================================================================

# Copy the rest of the application code into the container
# This layer changes frequently, so it comes after dependencies
COPY . .

# ============================================================================
# Runtime Configuration
# ============================================================================

# Document that the container listens on port 8000
# This is informational - you still need to map the port in docker-compose
EXPOSE 8000

# Default command to run when the container starts
# Runs Django's development server, bound to all interfaces (0.0.0.0)
# so it's accessible from outside the container
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
