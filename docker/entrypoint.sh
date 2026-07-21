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

# Emit the reserved ABORT signal (req-tap-logging-abort-signal / req-boot-abort-signal)
# for the bash-driven standup steps, mirroring tap.logging.abort() for the Python
# ones. A supervising watcher (scripts/spawn-session.sh Step 5, scripts/gate-lean)
# tails the container log for this exact `TAP-ABORT:` prefix and fast-fails the
# instant it appears, instead of waiting out its readiness timeout.
emit_abort() { echo "TAP-ABORT: $1: $2" >&2; }

echo "==> Syncing Python dependencies (uv sync --all-packages)..."
# --all-packages installs every workspace member and its deps into the venv,
# so plugin-local third-party requirements (declared in
# plugins/<slug>/pyproject.toml under req-plugin-arch-python-deps) land in
# the runtime env. Without this flag, members' deps stay in uv.lock but never
# get installed.
uv sync --all-packages

# ---------------------------------------------------------------------------
# FIPS boot self-check (req-cicd-base-image-lifecycle-6, decision D15) — fail closed.
# ---------------------------------------------------------------------------
# The image DECLARES its FIPS posture (org.tap.fips label + TAP_FIPS_MODE env); this PROVES
# the declared mode is the mode actually enforced by executing crypto and observing a refusal
# — never by inspecting files, because the FIPS boundary is the OpenSSL config, not the
# modules directory (doc-fips-assessment-record.md L13). Runs AFTER uv sync so `cryptography`
# (the webauthn/passkey integration point, built --no-binary against the system OpenSSL) is
# present. `tap.fips` prints its own `TAP-ABORT: fips: …` on a mismatch; this covers a hard
# process death. A FIPS-declared image that fails to refuse MD5 is the L1 fail-open trap, and
# a new bare hashlib.md5()/SELECT md5() in a dependency is a boot-breaking regression under
# FIPS — both are caught here before any schema mutation.
echo "==> FIPS self-check (assert declared mode is actually enforced)..."
if ! uv run python -m tap.fips; then
    emit_abort fips "FIPS self-check failed: declared mode not enforced (see above); refusing to serve"
    exit 1
fi

# ---------------------------------------------------------------------------
# System FIPS-provider gate (req-cicd-crypto-bom) — global validation, fail-closed.
# ---------------------------------------------------------------------------
# tap.fips proves the OpenSSL-backed Python layer is enforced, but it is blind to a plugin (or dep)
# that carries its OWN crypto — a Go binary, a Rust crate on ring/aws-lc-rs, a libsodium/pynacl wheel,
# a JVM — which ignores OPENSSL_CONF and would silently run non-FIPS crypto. When TAP_FIPS_MODE=1 this
# scans the WHOLE assembled environment (core + every installed plugin) and refuses to serve if any
# crypto provider is non-validated, UNLESS the operator has excused it with a justified `fips_waivers`
# entry in the boot profile (a plugin cannot excuse itself — only the deployer, with a reason). No-op
# when FIPS is off. Runs after uv sync so every plugin's closure is installed.
echo "==> System FIPS-provider gate (crypto-BOM: core + all plugins)..."
if ! uv run python -m tap.crypto_bom --gate --profile "${TAP_BOOT_PROFILE:-core_dev}"; then
    emit_abort crypto-bom "system FIPS-provider gate failed: a non-validated, un-waived crypto provider is present (see above); refusing to serve"
    exit 1
fi

# ---------------------------------------------------------------------------
# Bootstrap-tier secret-source providers (req-plugin-depres-bootstrap, Decision B).
# ---------------------------------------------------------------------------
# A plugin's git-install credential can be routed to an external store (e.g. AWS Secrets
# Manager) whose provider distribution must be importable BEFORE pre-boot resolves that
# credential. TAP_SECRET_SOURCE_DISTS is a space-separated list of `uv pip install` targets
# (local paths or requirements) installed into the venv here, ahead of pre-boot. It is
# UNSET in normal/dev boots, so no cloud SDK enters the default venv — this is the CI
# preinstall hook, not the general two-phase install engine (that stays deferred). Like
# pre-boot's own plugin installs, these persist across the subsequent `uv run` (its implicit
# sync is additive, not exact).
if [ -n "${TAP_SECRET_SOURCE_DISTS:-}" ]; then
    echo "==> Installing secret-source provider(s): ${TAP_SECRET_SOURCE_DISTS}"
    # shellcheck disable=SC2086  # intentional word-splitting on the space-separated list
    uv pip install ${TAP_SECRET_SOURCE_DISTS} || { emit_abort preboot "secret-source provider install failed"; exit 1; }
fi

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
echo "==> Pre-boot: installing declared plugins + pre-migrate snapshot (profile: ${TAP_BOOT_PROFILE:-core_dev})..."
if ! TAP_PLUGINS="$(uv run python -m tap.preboot --profile "${TAP_BOOT_PROFILE:-core_dev}")"; then
    # tap.preboot already emits its own `TAP-ABORT: preboot: …` on a PrebootError;
    # this covers the case where the process died without one (e.g. uv itself failed).
    emit_abort preboot "pre-boot stage failed; aborting standup before migrate (DB untouched)"
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
uv run python manage.py createcachetable || { emit_abort migrate "createcachetable failed"; exit 1; }

echo "==> Running database migrations..."
# The canonical fatal spot for a core->plugin-dep import leak (req-dev-validation-lean-boot):
# migrate runs django.setup(), which imports every INSTALLED_APPS module; a core module
# reaching a plugin-only dependency raises ModuleNotFoundError here. The sentinel turns that
# from a 300s readiness-timeout into a seconds-long fast-fail with the reason.
uv run python manage.py migrate --noinput || { emit_abort migrate "database migration failed (see traceback above)"; exit 1; }

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
