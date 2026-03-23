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
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

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
    # Core examples plugin — concept/precept types for demos and testing
    "plugins.core_examples.apps.CoreExamplesConfig",
    # LOTR plugin — Middle-earth entities for constraint testing
    "plugins.lotr.apps.LotrConfig",
    # API layer — last so ready() discovers all plugin routers
    "tap_api",
    # Web interface
    "tap_web",
    # Visualization
    "tap_viz",
    # History tracking — must be before tap_flip
    "simple_history",
    # FLIP — provenance, history, realms, environments
    "tap_flip",
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
# ImmediateBackend runs tasks synchronously in the same thread - fine for
# development and testing. For production, switch to a backend that runs
# tasks in a separate worker process.
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.ImmediateBackend",
    },
}
