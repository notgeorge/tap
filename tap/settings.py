"""
TAP Django Settings
=============================================================================
Single settings file using environment variables for configuration.
Defaults are set for local development via docker compose.

Key environment variables:
    DATABASE_URL    - PostgreSQL connection string
    DEBUG           - Enable debug mode (default: true for dev)
    SECRET_KEY      - Django secret key (MUST change in production)
    ALLOWED_HOSTS   - Comma-separated list of allowed hostnames
    TAP_GRID_ID     - UUIDv7 identifying this TAP installation (required)
"""

import json
import os
import sys
from pathlib import Path

import dj_database_url

# tap_auth owns the declaration of allauth's INSTALLED_APPS entries (the
# django-oscar pattern); settings spreads it below. Import-safe: a bare list
# constant, no Django access at module top.
from tap_auth.installed import ALLAUTH_APPS

# =============================================================================
# Paths
# =============================================================================
# BASE_DIR points to the project root (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# Security
# =============================================================================
# SECRET_KEY is used by Django for cryptographic signing:
#   - Session cookies (prevents tampering)
#   - CSRF tokens (prevents cross-site request forgery)
#   - Password reset tokens (prevents forging)
# If it changes, all active sessions are invalidated.
# If it leaks, an attacker could forge sessions and impersonate users.
# MUST be unique per installation and NEVER committed to version control.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,.localhost").split(",")

# =============================================================================
# TAP Grid Identity
# =============================================================================
# Every TAP installation has a globally unique Grid ID (UUIDv7).
# This value is stamped on every Entity as originating_grid_id,
# enabling future federation between TAP instances.
#
# One install = one Grid. This is an immutable identity for the lifetime
# of the installation, similar to how WordPress treats a single site.
#
# Generate one with: docker compose exec web uv run python manage.py generate_grid_id
TAP_GRID_ID = os.environ.get("TAP_GRID_ID", "")

if "runserver" in sys.argv:
    if TAP_GRID_ID:
        print(f"\n  TAP Grid ID: {TAP_GRID_ID}\n")
    else:
        print(
            "\n"
            "WARNING: TAP_GRID_ID is not set.\n"
            "Run: docker compose exec web uv run python manage.py generate_grid_id\n"
            "Then add the generated value to your docker-compose.yml environment.\n"
        )

# User-facing product name. Override via the TAP_PRODUCT_NAME env var.
TAP_PRODUCT_NAME = os.environ.get("TAP_PRODUCT_NAME", "RAMPART")

# Session label for multi-session dev disambiguation. When set, the UI prefixes
# the page title and nav with "[<label>]" so the developer can see at a glance
# which isolated stack a browser tab is pointing at. Empty for the primary stack.
# Set per-worktree in .env.local — see specs/spec-dev-multisession.md.
TAP_SESSION_LABEL = os.environ.get("TAP_SESSION_LABEL", "")

# =============================================================================
# tap-cares Runtime Secrets
# =============================================================================
# Root directory tap-cares scans for `*.secret.json` files at startup.
# Files live OFF the grid — values stay in memory once loaded, never on disk
# in the repo or in any TAP-managed node.
#
# Default points at the Compose bind mount declared in docker-compose.yml.
# If the directory is missing or empty the loader logs and returns; TAP starts
# normally and capabilities that need a missing secret fail at run time.
#
# See tap_cares/specs/spec-tap-cares-secrets.md.
TAP_SECRETS_ROOT = os.environ.get("TAP_SECRETS_ROOT", "/run/tap-secrets")

# =============================================================================
# Application Definition
# =============================================================================

# Package-mode plugins (req-boot-install-section). The settings-free pre-boot stage
# (tap/preboot.py, run in docker/entrypoint.sh BEFORE Django starts) installs the boot
# profile's `install` plugins, verifies each entry-point key == slug (the conformance
# gate), and emits their AppConfig dotted paths as the space-separated TAP_PLUGINS env
# var. The runserver + steady_queue processes are children of the entrypoint, so they
# inherit that env and CONSUME it directly (no discovery). They are spliced into
# INSTALLED_APPS just before tap_api.
#
# But TAP_PLUGINS is process-env state: a `manage.py` command run via a SEPARATE
# `docker exec` (spawn's `manage.py boot`, a manual `import_plugin_grift`, pytest) does
# NOT inherit it and would otherwise load none of the package-mode plugins. So when the
# env var is *unset* (as opposed to set-but-empty, which is a real "no package plugins"
# signal from the entrypoint), fall back to the SAME entry-point discovery pre-boot ran.
# Discovery reads installed distribution metadata, so it is self-consistent with the venv
# (never stale the way a cached file would be) and yields exactly the plugins this
# instance installed. This keeps every container process — server, boot, tests — agreeing
# on the package-mode set without each exec site having to re-pass TAP_PLUGINS.
_tap_plugins_env = os.environ.get("TAP_PLUGINS")
if _tap_plugins_env is not None:
    TAP_PLUGINS_APPS = _tap_plugins_env.split()
else:
    from tap.preboot import discover_entry_points

    # sorted() for a deterministic load order among package-mode plugins; inter-plugin
    # ordering (depends_on) is the deferred boot-consistency resolver's job.
    TAP_PLUGINS_APPS = sorted(discover_entry_points().values())

INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # django.contrib.sites — required by django-allauth (SITE_ID below). One
    # Site row per install; allauth resolves provider apps + callback URLs
    # against it.
    "django.contrib.sites",
    # NOTE: django-allauth is listed LATER, AFTER the tap apps (see the allauth
    # block below tap_viz). APP_DIRS template resolution is first-match-wins, so
    # the auth-owning apps (tap_auth, tap_web) must PRECEDE allauth for their
    # templates to override allauth's defaults. tap_auth owns the auth page
    # templates; tap_web owns the shared auth-UI styling.
    # TAP apps (added as we scaffold each one)
    # tap_boot is the bootloader and the cross-cutting management plane; it owns
    # all boot logic and sits FIRST so nothing below it imports the (deferred)
    # section-handler registry. It has no models/migrations, so leading the list
    # does not disturb the AUTH_USER_MODEL dependency root below
    # (spec-tap-boot-v0, req-boot-app-4).
    "tap_boot",
    # tap_health owns the health domain: the probe registry, the run_health()
    # service, `manage.py health`, and the boot-time provisioning system check.
    # No models/migrations; registers the core probes from its ready().
    "tap_health",
    # tap_auth owns AUTH_USER_MODEL and loads before tap_grid so the swapped
    # user model is a clean dependency root for every app's first migration
    # (req-tap-auth-app, req-tap-auth-user-model-6).
    "tap_auth",
    "tap_grid",
    "tap_plugins",
    # tap_cares — runtime plumbing for collectors/receivers/emitters/actions/schedules.
    # Loaded before plugins so collector_registry exists when plugin AppConfigs ready().
    "tap_cares.apps.TapCaresConfig",
    # Administrivia plugin — migrated to package-mode 2026-07-01
    # (tap_plugin.administrivia); loads via TAP_PLUGINS_APPS from the profile
    # `install` section.
    # LOTR plugin — migrated to package-mode 2026-07-01 (tap_plugin.lotr).
    # Still the load-bearing test-fixture vocabulary for the core tap_grid/
    # tap_api constraint/edge/validation suites (~20 modules import
    # tap_plugin.lotr.models), so it MUST be installed (editable) in any env
    # that runs those suites. Loads via TAP_PLUGINS_APPS from a profile
    # `install` section + the test-settings entry-point discovery-fallback;
    # its Middle-earth *seed data* remains instance clutter decoupled from the
    # app registration. See the lotr-vs-genericom note.
    # Computing Core plugin — migrated to package-mode 2026-07-01
    # (tap_plugin.computing_core); loads via TAP_PLUGINS_APPS.
    # AWS Core plugin — migrated to package-mode 2026-07-01 (tap_plugin.aws_core);
    # Tier-0 boto3 dep travels with the plugin. Loads via TAP_PLUGINS_APPS.
    # GitHub Core plugin — migrated to package-mode 2026-07-01
    # (tap_plugin.github_core). Loads via TAP_PLUGINS_APPS from the profile
    # `install` section; its PyYAML Tier-0 dep rides with the plugin (removed
    # from [tool.uv.workspace] members). Models account/repo/workflow/run/job/
    # runner; collector lands REFERENCES_RESOURCE links against aws_core nodes.
    # Sigstore Core plugin — migrated to package-mode 2026-07-01
    # (tap_plugin.sigstore_core); Tier-0 sigstore dep travels with the plugin.
    # Library plugin (rekor_log_entry/sigstore_ca models + verify/decompose
    # helpers) consumed by samsite's compliance_collector. Loads via
    # TAP_PLUGINS_APPS from the profile `install` section.
    # Genericom plugin — DEPRECATED 2026-05-19: 100% hand-built mock AWS
    # dataset (lotr-lineage scaffolding) built on aws_core. Code retained in
    # plugins/genericom/ but NOT loaded — real-account work (samsite)
    # supersedes it. Re-add this line to revive.
    # "plugins.genericom.apps.GenericomConfig",
    # ROSCALE plugin — migrated to package-mode 2026-07-01 (tap_plugin.roscale).
    # Install-only (registers the roscale-oscal-workbench panel types samsite's
    # compliance pages consume); loads via TAP_PLUGINS_APPS from the profile
    # `install` section.
    # Samsite plugin — migrated to package-mode 2026-07-01 (tap_plugin.samsite);
    # the demo integration surface (projection of the live AWS cross-deployment
    # of samaydlette.com). Loads via TAP_PLUGINS_APPS from the profile `install`
    # section; depends on sigstore_core/github_core/roscale/aws_core at import
    # time, installed before it (see boot/samsite.boot.json).
    # FedRAMP 20x KSI plugin — migrated to package-mode 2026-07-01 (first namespaced
    # plugin: tap_plugin.fedramp_20x_ksi). No longer build-baked here; it loads via
    # TAP_PLUGINS_APPS below after the pre-boot stage uv-installs it from the profile
    # `install` section. See docs/misc/doc-plugin-source-identity-deps-handoff.md.
    # Gryphon Playground plugin — migrated to package-mode 2026-07-02
    # (tap_plugin.gryphon_playground); the LAST build-baked plugin, closing the
    # initial plugin migration (BUILD_BAKED_PLUGIN_SLUGS now empty). pg_* playground
    # vocabulary + the Gridkin scenario corpus (a load-bearing test-fixture plugin,
    # like lotr). Loads via TAP_PLUGINS_APPS from a profile `install` section
    # (install-only — the corpus carries no GRIFT population seed).
    # Package-mode plugins installed by the pre-boot stage (TAP_PLUGINS). Spliced in
    # here — after build-baked plugins, before tap_api — so tap_api's ready() still
    # discovers their routers and their EntityTypes/edges register before the API/web
    # layers. Empty list when TAP_PLUGINS is unset. See TAP_PLUGINS_APPS above.
    *TAP_PLUGINS_APPS,
    # API layer — last so ready() discovers all plugin routers
    "tap_api",
    # Web interface
    "tap_web",
    # Visualization
    "tap_viz",
    # Authentication (django-allauth) — the login/social-login ENGINE behind the
    # /auth/ routes (req-tap-auth-app-3). tap_auth owns the routes, provider
    # config, security adapter, and policy (the Python) AND the declaration of
    # these app entries (tap_auth/installed.py — the django-oscar pattern); tap_web
    # owns ALL the auth PAGE TEMPLATES + styling (web rendering is tap_web's job —
    # tap_auth ships no templates, so there is no render path from the Internet
    # into the auth core); allauth is the engine. Spread here, AFTER the tap apps,
    # so tap_web wins template resolution (APP_DIRS first-match-wins) and overrides
    # allauth's defaults; allauth's own templates remain the fallback for any page
    # TAP does not override. Migrations are order-independent (the swappable
    # AUTH_USER_MODEL dep sequences tap_auth.User before allauth's user FKs), and
    # no tap app imports allauth at AppConfig-load time.
    *ALLAUTH_APPS,
    # History tracking (django-simple-history)
    "simple_history",
    # Steady Queue — production-equivalent task backend for django.tasks
    # and the once-per-minute scheduler tick (via @recurring). See
    # tap_cares/specs/spec-tap-cares-task-backend.md.
    "steady_queue",
]

# =============================================================================
# Logging
# =============================================================================
# Single LOGGING dict assembled from per-component contributions. See
# specs/spec-tap-logging.md (req-tap-logging-config-location). Override
# per-logger levels at runtime with TAP_LOG_LEVELS=name=LEVEL,name=LEVEL,...;
# override the root logger with TAP_LOG_LEVEL=LEVEL.
from tap.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(INSTALLED_APPS)

MIDDLEWARE = [
    # Dev-only: no-store on page responses so reloads pick up edits (the
    # runserver_nocache command covers /static/, which bypasses middleware).
    # Outermost so it has the final say on Cache-Control; inert when DEBUG is off.
    "tap_web.middleware.DevNoStoreMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Bind a TAP CallerContext from request.user (after AuthenticationMiddleware
    # populates it) so the service boundary can authorize the request actor
    # (req-tap-auth-service-boundary). Must precede any view that reads the grid.
    "tap_auth.middleware.CallerContextMiddleware",
    # allauth account middleware — required by django-allauth (handles account
    # state / login-flow redirects). Must follow AuthenticationMiddleware.
    "allauth.account.middleware.AccountMiddleware",
    # Default-deny login wall (req-tap-auth-service-boundary, launch-ready
    # "auth enforced"). Subclasses Django's LoginRequiredMiddleware: every view
    # requires an authenticated session EXCEPT the path prefixes in
    # TAP_LOGIN_EXEMPT_PREFIXES (the login routes themselves, the API which
    # enforces its own session_auth → 401, Django admin which has its own login,
    # and static assets). New pages are protected by construction; forgetting a
    # gate fails closed (redirect to login), not open.
    "tap_auth.middleware.TapLoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tap.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tap_web.context_processors.branding",
                "tap_web.navigation.breadcrumb",
            ],
        },
    },
]

WSGI_APPLICATION = "tap.wsgi.application"

# =============================================================================
# Database
# =============================================================================
# Configured via DATABASE_URL environment variable.
# docker-compose.yml sets this to: postgres://tap:tap@db:5432/tap
#
# dj_database_url.config() parses the URL into Django's DATABASES dict format.
# conn_max_age=600 keeps database connections open for 10 minutes,
# reducing the overhead of creating new connections on every request.
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://tap:tap@localhost:5432/tap",
        conn_max_age=600,
    ),
}

# search_readonly: same DB, PostgreSQL read-only session parameter set at connection
# time. Prevents writes at the database level for all search execution (req-grid-search-readonly.sec).
# TEST.MIRROR tells Django's test runner this alias shares the same physical DB as
# "default" so it skips creating/flushing a separate test database for it.
DATABASES["search_readonly"] = {
    **DATABASES["default"],
    "OPTIONS": {
        **DATABASES["default"].get("OPTIONS", {}),
        "options": "-c default_transaction_read_only=on",
    },
    "TEST": {"MIRROR": "default"},
}

# =============================================================================
# Authentication
# =============================================================================
# Canonical user model — owned by tap_auth (req-tap-auth-user-model). It lands in
# tap_auth's first migration with AUTH_USER_MODEL pointed here from the start;
# every FK uses settings.AUTH_USER_MODEL and runtime code uses get_user_model().
AUTH_USER_MODEL = "tap_auth.User"

# TAP_TEST_MODE — the single explicit "this process is the test runner" signal
# (req-tap-auth-actor-model). Default False here; tap/test_settings.py flips it
# True. Deliberately independent of DEBUG: DEBUG=True is the normal state of dev
# boxes / single-tenant deploys and must never imply test mode. Its v1 effect is
# to gate creation of test-only built-ins (e.g. the tap_test actor); enforcement
# behavior never depends on it.
TAP_TEST_MODE = False

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------------------------------------------
# Authentication backends + allauth (req-tap-auth-app, req-tap-auth-providers)
# -----------------------------------------------------------------------------
# TapModelBackend keeps local username/password (dev + recovery floor,
# req-tap-auth-local) and is what Django admin uses — but refuses password auth
# (everywhere, incl. admin) when TAP_LOCAL_PASSWORD_ENABLED is False, without
# deactivating users or killing sessions. allauth's backend adds the social/OIDC
# login path (unaffected by the toggle). Order: local first so it resolves
# without consulting allauth.
AUTHENTICATION_BACKENDS = [
    "tap_auth.auth_backends.TapModelBackend",
    "tap_auth.auth_backends.TapAllauthBackend",
]

# Single Site row per install (django.contrib.sites). allauth binds provider
# apps + derives callback URLs against it.
SITE_ID = 1

# Login wall (TapLoginRequiredMiddleware). LOGIN_URL is allauth's login view;
# unauthenticated requests to non-exempt paths redirect here. After login,
# users land on "/" (the landing page / their no-access notice if cap-less).
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"

# Path prefixes the login wall does NOT gate. Each has its own enforcement:
#   /auth/    — the login routes themselves (gating them would loop)
#   /api/     — Django-Ninja session_auth returns 401 for anon (not an HTML
#               login redirect, which would corrupt API clients)
#   /admin/   — Django admin has its own staff login + redirect
#   /static/, /favicon.ico — unauthenticated static assets
# Everything else requires an authenticated session.
TAP_LOGIN_EXEMPT_PREFIXES = [
    "/auth/",
    "/api/",
    "/admin/",
    "/static/",
    "/favicon.ico",
    # No /healthz: the unauthenticated health endpoint was parked
    # (req-tap-health-exposure-4). Health is introspected in-process via
    # `manage.py health`, so there is no unauthenticated surface to exempt.
]

# allauth security posture — pin the login-safety knobs explicitly rather than
# trusting defaults to stay favorable (req-tap-auth-external-identity).
#   LOGIN_ON_GET=False  → POST-only social login initiation (guards against
#                         login-CSRF / drive-by social login via a crafted link).
#   EMAIL_AUTHENTICATION=False → never auto-authenticate/auto-connect a social
#                         login to a local account by matching verified email;
#                         the TAP adapter owns same-email handling (deny → link
#                         disabled). Held at allauth's secure default, pinned.
# The concrete provider APPS list is built by the provider framework from the
# boot auth config + resolved secrets (req-tap-auth-providers); empty until then.
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False

# TAP-owned allauth adapters (req-tap-auth-external-identity). The social adapter
# is the login security chokepoint (verified-email / hd-domain / allowlist /
# linking-disabled, gated auto-provisioning, ExternalIdentity sync, initial-admin
# grant). The account adapter disables public local self-signup.
SOCIALACCOUNT_ADAPTER = "tap_auth.adapter.TapSocialAccountAdapter"
ACCOUNT_ADAPTER = "tap_auth.adapter.TapAccountAdapter"

# Human-facing user label (req-tap-auth-external-identity): allauth messages /
# UI show email, never the generated non-display username (ext-<provider>-<hash>).
ACCOUNT_USER_DISPLAY = "tap_auth.adapter.user_display"

# Declarative auth config comes from the boot profile's `auth` section
# (req-tap-auth-boot) — ONE declarative source feeds both the running server's
# settings (here) and the `manage.py boot` validation phase. A JSON env override
# wins for dev / pre-boot wiring. The profile id is TAP_BOOT_PROFILE (same env the
# bootloader reads). allauth's provider APPS are built from these at settings-build
# time so the resolved secret stays in memory, never a DB SocialApp row
# (req-tap-auth-providers-3).
_TAP_BOOT_PROFILE = os.environ.get("TAP_BOOT_PROFILE", "").strip()

from tap_auth.boot import (  # noqa: E402
    initial_admins_for_settings,
    initial_grants_for_settings,
    local_password_enabled_from_profile,
    providers_for_settings,
)
from tap_auth.providers import build_socialaccount_providers  # noqa: E402

# Public base URL (scheme + host[:port]). Required when external providers are
# configured (req-tap-auth-providers-7): provider callback URLs derive from it.
# allauth derives the runtime redirect_uri from the request; this is the
# canonical value provider self-tests and boot validation use.
TAP_BASE_URL = os.environ.get("TAP_BASE_URL", "")

_env_providers = os.environ.get("TAP_AUTH_PROVIDERS")
TAP_AUTH_PROVIDERS = json.loads(_env_providers) if _env_providers else providers_for_settings(_TAP_BOOT_PROFILE)
SOCIALACCOUNT_PROVIDERS = build_socialaccount_providers(TAP_AUTH_PROVIDERS)

# Verified emails granted tap_admin on first login (req-tap-auth-boot). Add-only
# (a typo cannot revoke admin). From the boot profile's auth section; env override
# for dev. Operator-controlled — never a plugin. Retained for the last-admin
# invariant's readability and as documented sugar; the adapter grants via
# TAP_AUTH_INITIAL_GRANTS below (which folds these in).
_env_admins = os.environ.get("TAP_AUTH_INITIAL_ADMINS")
TAP_AUTH_INITIAL_ADMINS = json.loads(_env_admins) if _env_admins else initial_admins_for_settings(_TAP_BOOT_PROFILE)

# Effective email -> roles grant map applied on each login (req-tap-auth-boot,
# req-tap-auth-roles). Generalizes initial_admins to any human-assignable role
# (tap_admin, tap_viewer) and folds initial_admins in as {email: ["tap_admin"]}.
# Add-only/idempotent; the adapter refuses any non-human-assignable role even if
# one leaks past the schema. Env override (JSON object) for dev.
_env_grants = os.environ.get("TAP_AUTH_INITIAL_GRANTS")
TAP_AUTH_INITIAL_GRANTS = json.loads(_env_grants) if _env_grants else initial_grants_for_settings(_TAP_BOOT_PROFILE)

# Local Django password login (dev + recovery floor — req-tap-auth-local). From
# the boot profile's auth section (default True); env override for dev. When
# False, local password login is blocked everywhere incl. Django admin (enforced
# by the local-auth-disable backend in increment 5).
_env_local = os.environ.get("TAP_LOCAL_PASSWORD_ENABLED")
TAP_LOCAL_PASSWORD_ENABLED = (
    _env_local.strip().lower() in ("true", "1", "yes")
    if _env_local is not None
    else local_password_enabled_from_profile(_TAP_BOOT_PROFILE)
)

# Local account behavior (dev + recovery). Email optional/unverified locally;
# external IdP login is the customer path (req-tap-auth-local).
ACCOUNT_LOGIN_METHODS = {"username"}
ACCOUNT_EMAIL_VERIFICATION = "none"

# -----------------------------------------------------------------------------
# Sessions & cache — DB-backed, no external cache (hot-swap-survivable)
# -----------------------------------------------------------------------------
# Sessions live in Postgres so a web-container hot-swap loses no logins, and so
# the session-invalidation banhammer (req-tap-auth-sessions) operates on the
# real Django session store. Cache is the DB backend too (DatabaseCache) — the
# OIDC discovery-doc cache and allauth rate-limit state survive a swap with no
# Redis/Memcached dependency. createcachetable provisions the table (run in
# boot/migrate; tests override CACHES to locmem in tap/test_settings.py).
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "tap_cache",
    },
}

# =============================================================================
# Internationalization
# =============================================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# =============================================================================
# Static Files
# =============================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# No project-level static/ dir — each app ships its own static/ (collected by
# AppDirectoriesFinder). Declaring BASE_DIR/"static" here only produced a
# staticfiles.W004 "directory does not exist" check warning on every command.
STATICFILES_DIRS: list = []

# =============================================================================
# Default Primary Key Type
# =============================================================================
# UUIDv7 is TAP's standard for entity IDs, but Django's auto-incrementing
# BigAutoField is fine for internal Django models (sessions, admin logs, etc.)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# Background Tasks (Django 6 built-in)
# =============================================================================
# Django 6 includes a built-in tasks framework (django.tasks) that replaces
# the need for Celery in most cases. It provides the API for defining and
# queuing tasks, while backends handle execution.
#
# Dev / prod default: Steady Queue
# (req-tap-cares-task-backend-steady-queue-1). Steady Queue is a Solid Queue
# port that implements the django.tasks TaskBackend interface and runs
# against the existing Postgres database with no extra infrastructure.
#
# Tests use ImmediateBackend (synchronous, same-thread) via tap/test_settings.py
# so post-task assertions don't need to wait for worker pickup
# (req-tap-cares-task-backend-test-settings-1).
TASKS = {
    "default": {
        "BACKEND": "steady_queue.backend.SteadyQueueBackend",
        "QUEUES": ["default", "scheduler"],
        "OPTIONS": {},
    },
}

# =============================================================================
# Steady Queue configuration
# =============================================================================
# Worker / queue split per req-tap-cares-task-backend-queue-isolation:
#   - scheduler queue, 1 thread: dedicated lane for the once-per-minute
#     scheduler tick. Isolated from collector workload so a backed-up
#     collector pool cannot starve the clock.
#   - default queue, 3 threads: collectors and any other background work.
#
# The supervisor forks one process per Worker config, giving OS-level
# isolation between the two queues. See
# tap_cares/specs/spec-tap-cares-task-backend.md for details, including the
# heuristic for when to revisit threads=3.
from datetime import timedelta  # noqa: E402

from steady_queue.configuration import Configuration  # noqa: E402

STEADY_QUEUE = Configuration.Options(
    dispatchers=[
        Configuration.Dispatcher(
            polling_interval=timedelta(seconds=1),
            batch_size=500,
        ),
    ],
    workers=[
        Configuration.Worker(
            queues=["scheduler"],
            threads=1,
            polling_interval=timedelta(seconds=0.1),
        ),
        Configuration.Worker(
            queues=["default"],
            threads=3,
            polling_interval=timedelta(seconds=0.1),
        ),
    ],
)
