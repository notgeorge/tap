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

TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    },
}

LOGGING = copy.deepcopy(_LOGGING)
for _entry in LOGGING.get("loggers", {}).values():
    _entry["propagate"] = True
del _entry
