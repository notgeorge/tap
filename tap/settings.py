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

import os
import sys
from pathlib import Path

import dj_database_url

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

# User-facing product name. Override to rebrand the UI (e.g. "Rampart").
TAP_PRODUCT_NAME = os.environ.get("TAP_PRODUCT_NAME", "TAP")

# Session label for multi-session dev disambiguation. When set, the UI prefixes
# the page title and nav with "[<label>]" so the developer can see at a glance
# which isolated stack a browser tab is pointing at. Empty for the primary stack.
# Set per-worktree in .env.local — see specs/spec-dev-multisession.md.
TAP_SESSION_LABEL = os.environ.get("TAP_SESSION_LABEL", "")

# =============================================================================
# Application Definition
# =============================================================================
INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # TAP apps (added as we scaffold each one)
    "tap_grid",
    "tap_plugins",
    # tap_cares — runtime plumbing for collectors/receivers/emitters/actions/schedules.
    # Loaded before plugins so collector_registry exists when plugin AppConfigs ready().
    "tap_cares.apps.TapCaresConfig",
    # Administrivia plugin — TAP administrative pages and infrastructure
    "plugins.administrivia.apps.AdministriviaConfig",
    # LOTR plugin — Middle-earth entities for constraint testing
    "plugins.lotr.apps.LotrConfig",
    # Computing Core plugin — vendor-neutral computing primitives
    "plugins.computing_core.apps.ComputingCoreConfig",
    # AWS Core plugin — resource-type models for AWS cloud infrastructure
    "plugins.aws_core.apps.AwsCoreConfig",
    # Genericom plugin — demonstration AWS environment built on aws_core
    "plugins.genericom.apps.GenericomConfig",
    # FedRAMP 20x KSI plugin — Key Security Indicator catalog
    "plugins.fedramp_20x_ksi.apps.Fedramp20xKsiConfig",
    # API layer — last so ready() discovers all plugin routers
    "tap_api",
    # Web interface
    "tap_web",
    # Visualization
    "tap_viz",
    # History tracking (django-simple-history)
    "simple_history",
    # Huey periodic-task framework — being phased out; replaced by Steady
    # Queue's @recurring in the next migration commit. Kept for now so the
    # backend swap can land in isolation and roll back cleanly if needed.
    "huey.contrib.djhuey",
    # Steady Queue — production-equivalent task backend for django.tasks.
    # See tap_cares/specs/spec-tap-cares-task-backend.md.
    "steady_queue",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
# Custom user model - MUST be set before the first migration.
# This extends AbstractUser so we can add fields later without painful migrations.
# Changing this after migrations have been created is extremely difficult,
# which is why we set it up from day one even if the initial model is minimal.
AUTH_USER_MODEL = "tap_grid.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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
STATICFILES_DIRS = [BASE_DIR / "static"]

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

# =============================================================================
# Huey configuration — tap_cares scheduler (being phased out)
# =============================================================================
# Huey is being replaced by Steady Queue's @recurring in the next migration
# commit (req-tap-cares-task-backend-huey-removal). Kept here for now so this
# commit can land the Steady Queue backend swap in isolation and roll back
# cleanly if needed.
HUEY = {
    "huey_class": "huey.MemoryHuey",
    "name": "tap_cares_scheduler",
    "immediate": False,
    "consumer": {
        "workers": 1,
        "worker_type": "thread",
        "periodic": True,
    },
}
