"""Test settings — inherits from tap.settings and overrides only what tests need.

Used by pytest via the `DJANGO_SETTINGS_MODULE = "tap.test_settings"` line in
`pyproject.toml`'s `[tool.pytest.ini_options]`. The container entrypoint and
management commands continue to default to `tap.settings`.

Per `tap_cares/specs/spec-tap-cares-task-backend.md`
`req-tap-cares-task-backend-test-settings`: tests use `ImmediateBackend` for
`TASKS["default"]["BACKEND"]` so synchronous-completion semantics are
preserved. Existing tests that rely on `run_collection` reaching a terminal
state before returning continue to work without modification.

Per `specs/spec-tap-logging.md` `req-tap-logging-config-location-3`:
`test_settings.py` may override individual logger entries. Here we flip
`propagate` to True on every configured logger so pytest's `caplog` fixture
(which attaches its handler to the root logger) can capture records that
production has configured as `propagate=False`.
"""

from __future__ import annotations

import copy

from tap.settings import *  # noqa: F401, F403
from tap.settings import LOGGING as _LOGGING

# Package-mode plugins load under pytest via tap.settings itself: pytest runs Django
# directly (never the pre-boot stage), so TAP_PLUGINS is unset and settings falls back
# to entry-point discovery — loading exactly the package-mode plugins editable-installed
# in the venv (e.g. fedramp_20x_ksi under the samsite profile). No plugin-loading logic
# is needed here. See tap/settings.py TAP_PLUGINS_APPS.

# This process IS the test runner (req-tap-auth-actor-model). The only signal
# that gates creation of test-only built-ins such as the tap_test actor.
TAP_TEST_MODE = True

TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    },
}

# Cache: local-memory in tests (no DatabaseCache table to provision; tests need
# no cross-process / hot-swap survival). Production uses DatabaseCache — see
# tap.settings CACHES and the no-external-cache posture.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

LOGGING = copy.deepcopy(_LOGGING)
for _entry in LOGGING.get("loggers", {}).values():
    _entry["propagate"] = True
del _entry

# Passkey ceremony tests need a deterministic RP-ID + exact origin; the vendored
# virtual authenticator signs for this exact origin (req-tap-auth-passkey-webauthn-7).
TAP_PASSKEY_RP_ID = "localhost"
TAP_PASSKEY_ORIGIN = "http://localhost:8090"
