"""Test settings — inherits from tap.settings and overrides only what tests need.

Used by pytest via the `DJANGO_SETTINGS_MODULE = "tap.test_settings"` line in
`pyproject.toml`'s `[tool.pytest.ini_options]`. The container entrypoint and
management commands continue to default to `tap.settings`.

Per `tap_cares/specs/spec-tap-cares-task-backend.md`
`req-tap-cares-task-backend-test-settings`: tests use `ImmediateBackend` for
`TASKS["default"]["BACKEND"]` so synchronous-completion semantics are
preserved. Existing tests that rely on `run_collection` reaching a terminal
state before returning continue to work without modification.
"""

from __future__ import annotations

from tap.settings import *  # noqa: F401, F403

TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
    },
}
