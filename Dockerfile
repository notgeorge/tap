# TAP Development Dockerfile
#
# Base image: a curated-minimal Wolfi base (cgr.dev/chainguard/wolfi-base) carrying exactly
# TAP's runtime binaries, per req-cicd-base-image-lifecycle-3 (Wolfi is the standard base,
# decided 2026-07-09; spike measured OS-CVEs 311→0 vs the outgoing python:3.14-slim). Wolfi
# is glibc-based, so manylinux Python wheels install without a source build. It is chosen on
# Python-3.14 currency, in-image host-independent FIPS (req-cicd-base-image-lifecycle-5/-6),
# and a zero-CVE floor — NOT on shipping a runtime package manager (TAP's deps + plugins are
# Python-package installs baked/synced by uv, not OS-package installs; see the assessment
# record docs/misc/doc-fips-assessment-record.md L11 and distroless disproof spikes/distroless/).
#
# This stages the cutover: this revision swaps the base to Wolfi with FIPS OFF (TAP_FIPS=0),
# validating the base swap in isolation. FIPS-on (the fips.so builder stage + provider config +
# fail-closed boot assertion) lands in a subsequent commit so a boot break is attributable to
# the apk swap vs the provider config, not both at once (req-cicd-base-image-lifecycle-6).
FROM cgr.dev/chainguard/wolfi-base

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

# Install system-level runtime binaries. These are named, itemized attack-surface
# line-items (req-cicd-base-image-lifecycle-3), present because the runtime-plugin-install
# architecture requires them, and kept current by the auto-patch loop (-1).
# - python-3.14: the interpreter (Wolfi ships /usr/bin/python -> python3 -> python3.14).
# - git: uv shells out to it to install package-mode plugins from a git source
#   (`<dist> @ git+https://…@<rev>`, req-boot-install-section). Wolfi's git porcelain in
#   /usr/libexec/git-core are shell scripts that need sed/grep — both present via busybox
#   on wolfi-base (verified), so no extra apk is required (assessment record L3).
# - bash: the entrypoint (docker/entrypoint.sh) is a bash script.
# - postgresql-client: pg_isready/psql for Django, AND pg_dump/pg_restore for the pre-boot
#   pre-migrate snapshot (tap/preboot.py, req-boot-snapshot). Wolfi ships 18.x; a newer
#   pg_dump dumps the older PG16 server fine.
# - curl: used by docker/install-tailwindcss.sh; also handy for in-container debugging.
# - tzdata: the IANA timezone database (/usr/share/zoneinfo). Debian's python:3.14-slim
#   shipped this implicitly; Wolfi's minimal base does not, and without it Python's
#   `zoneinfo` cannot resolve settings.TIME_ZONE ("UTC") — Django's createcachetable /
#   timezone machinery aborts boot with ZoneInfoNotFoundError. It is OS timezone data, not
#   the PyPI `tzdata` shim, so it serves every in-image consumer, not just Python.
RUN apk add --no-cache \
    python-3.14 \
    git \
    bash \
    postgresql-client \
    curl \
    tzdata

# ============================================================================
# UV Package Manager
# ============================================================================

# Copy UV binary from the official UV container image
# UV is a fast Python package manager written in Rust (replaces pip)
# This is the recommended way to install UV in Docker — no package manager needed.
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
