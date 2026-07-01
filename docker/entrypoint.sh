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
# Exit immediately if any command failsals
set -e

echo "==> Syncing Python dependencies (uv sync --all-packages)..."
# --all-packages installs every workspace member and its deps into the venv,
# so plugin-local third-party requirements (declared in
# plugins/<slug>/pyproject.toml under req-plugin-arch-python-deps) land in
# the runtime env. Without this flag, members' deps stay in uv.lock but never
# get installed.
uv sync --all-packages

# ---------------------------------------------------------------------------
# Pre-boot stage (settings-free; runs BEFORE Django reads settings).
# ---------------------------------------------------------------------------
# tap/preboot.py reads the boot profile as plain JSON, uv-installs the profile's
# `install` plugins (idempotent — a reboot is a fast no-op, no re-pull), verifies
# each plugin's entry-point key == slug, runs the static coherence guard, and takes
# a verified pre-migrate DB snapshot (switch defaults true; dev disables it via
# TAP_BOOT_INSTALL__SNAPSHOT_BEFORE_MIGRATE=false in .env.local). It prints the
# resolved package-mode AppConfig paths on stdout as TAP_PLUGINS, which settings.py
# consumes (splicing them into INSTALLED_APPS before tap_api). This runs before
# createcachetable/migrate so the snapshot precedes ALL schema changes and so
# TAP_PLUGINS is set for migrate + the server. A pre-boot failure is fatal and
# aborts here, before any schema mutation, leaving the DB untouched (req-boot-preboot).
# It is the Kubernetes initContainers shape: a run-to-completion stage before the
# main process. `manage.py boot` (population) still runs at spawn time.
echo "==> Pre-boot: installing declared plugins + pre-migrate snapshot (profile: ${TAP_BOOT_PROFILE:-base})..."
if ! TAP_PLUGINS="$(uv run python -m tap.preboot --profile "${TAP_BOOT_PROFILE:-base}")"; then
    echo "FATAL: pre-boot stage failed; aborting standup before migrate (DB untouched)." >&2
    exit 1
fi
export TAP_PLUGINS
echo "==> Pre-boot complete. TAP_PLUGINS=[${TAP_PLUGINS:-<none>}]"

# Provision the DatabaseCache table (settings.CACHES LOCATION="tap_cache").
# This is DB-schema provisioning, the same category as migrate — "fresh DB →
# schema current" — not instance state, so it lives here next to migrate rather
# than in `manage.py boot` (which converges instance state above the schema) or
# in spawn-session.sh (dev-env orchestration only). createcachetable is
# idempotent: it no-ops when the table already exists, so it is safe on every
# container start. Without it the first cache read (e.g. allauth login
# rate-limiting) fails with relation "tap_cache" does not exist.
#
# This MUST run BEFORE migrate: the `tap_health.E001` Tags.database system check
# (tap_health/checks.py) fires during migrate's check phase and hard-fails when
# the cache table is missing, so on a fresh DB `migrate` would abort before this
# step ever ran (chicken-and-egg → container restart loop). createcachetable
# itself has `requires_system_checks = []`, so it runs no checks and is safe
# against an as-yet-unmigrated DB; it creates the table via the schema editor
# independently of migration state.
echo "==> Provisioning the DatabaseCache table (createcachetable)..."
uv run python manage.py createcachetable

echo "==> Running database migrations..."
uv run python manage.py migrate --noinput

# Note: tailwindcss is NOT rebuilt at container start. The committed
# tap_web/static/tap_web/css/tailwind.css is served as-is. Dev work that
# touches Tailwind utility classes is expected to invoke the
# /tailwind-rebuild skill (tap_web/skills/tailwind-rebuild/SKILL.md), which
# orchestrates an on-demand install + build inside this container and
# commits the regenerated file alongside the template change. See
# tap_web/specs/spec-web-tailwind-pipeline.md.

# Start the Steady Queue supervisor as a background process. It runs both
# the once-per-minute scheduler tick (declared as a @recurring task in
# tap_cares/task_backend.py) and the collector execution tasks. The
# supervisor forks one worker process per Configuration.Worker in
# settings.STEADY_QUEUE — one for the scheduler queue, one for the default
# queue — giving OS-level isolation between the clock and collector
# execution (req-tap-cares-task-backend-queue-isolation). Trap kills it on
# exit. Steady Queue does NOT auto-reload; restart the container if you
# edit task or scheduler code (req-tap-cares-task-backend-deployment-3).
echo "==> Starting Steady Queue supervisor..."
uv run python manage.py steady_queue &
STEADY_QUEUE_PID=$!

trap "kill ${STEADY_QUEUE_PID} 2>/dev/null || true" EXIT

echo "==> Starting Django development server (no-store on static for live JS/CSS)..."
exec uv run python manage.py runserver_nocache 0.0.0.0:8000
