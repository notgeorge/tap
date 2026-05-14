"""tap_cares logging contributions.

Implements `req-tap-logging-component-libs` from `specs/spec-tap-logging.md`:
tap_cares owns the log level of `steady_queue` because tap_cares is the only
consumer — it imports `steady_queue` for the `@recurring` decorator in
`tap_cares/task_backend.py` and the entrypoint runs `manage.py steady_queue`
as the supervisor.

If a second consumer ever emerges, `steady_queue` becomes a candidate for
promotion to `tap.logging._FOUNDATIONAL_LOGGERS`.
"""

from __future__ import annotations

from typing import Any


def app_logger_config() -> dict[str, dict[str, Any]]:
    return {
        "steady_queue": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    }
