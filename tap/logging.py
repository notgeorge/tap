"""TAP-wide logging configuration.

Implements `specs/spec-tap-logging.md`. Stage 1 — logger configuration only;
the site-ID scanner described in `req-tap-logging-site-id-scanner` lands in
Stage 2.

Public API:
    build_logging_config(installed_apps, env) -> dict
        Returns the dictConfig-shaped dict assigned to `settings.LOGGING`.
    plugin_logger_config(installed_apps) -> dict
        Returns logger configs for registered plugins plus the wildcard fallback.
        Exposed for tests; not normally called directly.

Builder merge order (`req-tap-logging-config-location-5`):
    1. First-party app loggers — req-tap-logging-app-loggers
    2. Foundational third-party loggers — req-tap-logging-foundational-loggers
    3. Per-app `<app>.logging.app_logger_config()` contributions — req-tap-logging-component-libs
    4. Per-plugin entries from INSTALLED_APPS — req-tap-logging-plugin-loggers
    5. Environment-variable overrides — req-tap-logging-env-overrides

Defensive printing rather than logging: this module configures the logging
system, so it cannot rely on it. Warnings about malformed env vars or broken
app helpers go to stderr directly.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Mapping

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(pathname)s:%(lineno)d — %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

# req-tap-logging-app-loggers — first-party apps with default levels.
# tap_flip and tap_ai are reserved (no app exists yet); inert until they do.
_FIRST_PARTY_APPS: dict[str, str] = {
    "tap_grid": "INFO",
    "tap_api": "INFO",
    "tap_cares": "INFO",
    "tap_web": "INFO",
    "tap_viz": "INFO",
    "tap_plugins": "INFO",
    "tap_flip": "INFO",
    "tap_ai": "INFO",
}

# req-tap-logging-foundational-loggers — libraries used transitively by anything
# with no single owner. Component-owned libraries (steady_queue, etc.) live in
# each component's <app>.logging.app_logger_config(); they are NOT listed here.
_FOUNDATIONAL_LOGGERS: dict[str, str] = {
    "django": "INFO",
    "django.db.backends": "WARNING",
    "django.server": "WARNING",
    "urllib3": "WARNING",
}

# req-tap-logging-plugin-loggers — wildcard catches plugins not explicitly
# configured (e.g. one mid-development that hasn't been added to INSTALLED_APPS).
_PLUGIN_WILDCARD_LEVEL = "INFO"

# req-tap-logging-env-overrides-4 — valid level set for env-var validation.
_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

_ENV_PER_LOGGER = "TAP_LOG_LEVELS"
_ENV_ROOT = "TAP_LOG_LEVEL"


def _logger_entry(level: str) -> dict[str, Any]:
    return {"level": level, "handlers": ["console"], "propagate": False}


def _first_party_logger_configs() -> dict[str, dict[str, Any]]:
    return {name: _logger_entry(level) for name, level in _FIRST_PARTY_APPS.items()}


def _foundational_logger_configs() -> dict[str, dict[str, Any]]:
    return {name: _logger_entry(level) for name, level in _FOUNDATIONAL_LOGGERS.items()}


def _discover_plugin_slugs(installed_apps: list[str]) -> list[str]:
    """Extract plugin slugs from INSTALLED_APPS, preserving order, de-duplicated.

    Plugin entries look like `plugins.<slug>.apps.<ConfigClass>` or `plugins.<slug>`.
    """
    slugs: list[str] = []
    seen: set[str] = set()
    for entry in installed_apps:
        parts = entry.split(".")
        if len(parts) < 2 or parts[0] != "plugins":
            continue
        slug = parts[1]
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def plugin_logger_config(installed_apps: list[str]) -> dict[str, dict[str, Any]]:
    """Return logger configs for registered plugins plus the wildcard fallback."""
    config: dict[str, dict[str, Any]] = {
        "plugins": _logger_entry(_PLUGIN_WILDCARD_LEVEL),
    }
    for slug in _discover_plugin_slugs(installed_apps):
        config[f"plugins.{slug}"] = _logger_entry("INFO")
    return config


def _discover_first_party_app_modules(installed_apps: list[str]) -> list[str]:
    """Return distinct tap_* app module names from INSTALLED_APPS, preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for entry in installed_apps:
        head = entry.split(".", 1)[0]
        if not head.startswith("tap_"):
            continue
        if head in seen:
            continue
        seen.add(head)
        out.append(head)
    return out


def _app_logger_configs(installed_apps: list[str]) -> dict[str, dict[str, Any]]:
    """Discover and merge `<app>.logging.app_logger_config()` contributions.

    Missing modules / missing helpers are silently skipped
    (req-tap-logging-component-libs-2). A helper that raises or returns the
    wrong shape produces a stderr warning and is skipped.
    """
    config: dict[str, dict[str, Any]] = {}
    for app in _discover_first_party_app_modules(installed_apps):
        module_name = f"{app}.logging"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        helper = getattr(module, "app_logger_config", None)
        if helper is None:
            continue
        try:
            contribution = helper()
        except Exception as exc:  # noqa: BLE001
            print(
                f"WARNING: {module_name}.app_logger_config() raised {exc!r}; skipping.",
                file=sys.stderr,
            )
            continue
        if not isinstance(contribution, dict):
            print(
                f"WARNING: {module_name}.app_logger_config() returned "
                f"{type(contribution).__name__}, expected dict; skipping.",
                file=sys.stderr,
            )
            continue
        config.update(contribution)
    return config


def _parse_env_overrides(env: Mapping[str, str]) -> tuple[dict[str, str], str | None]:
    """Parse TAP_LOG_LEVELS and TAP_LOG_LEVEL into (per_logger, root_level).

    Per-logger map: {logger_name: LEVEL}. Root level: LEVEL or None.
    Invalid entries are skipped with a stderr warning.
    """
    per_logger: dict[str, str] = {}

    raw_pairs = env.get(_ENV_PER_LOGGER, "")
    if raw_pairs:
        for raw_pair in raw_pairs.split(","):
            pair = raw_pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                print(
                    f"WARNING: {_ENV_PER_LOGGER} entry {pair!r} has no '='; skipping.",
                    file=sys.stderr,
                )
                continue
            name, _, raw_level = pair.partition("=")
            name = name.strip()
            level = raw_level.strip().upper()
            if not name:
                print(
                    f"WARNING: {_ENV_PER_LOGGER} entry {pair!r} has empty logger name; skipping.",
                    file=sys.stderr,
                )
                continue
            if level not in _VALID_LEVELS:
                print(
                    f"WARNING: {_ENV_PER_LOGGER} entry for {name!r} has invalid level "
                    f"{raw_level.strip()!r}; skipping.",
                    file=sys.stderr,
                )
                continue
            per_logger[name] = level

    root_level: str | None = None
    raw_root = env.get(_ENV_ROOT)
    if raw_root is not None:
        candidate = raw_root.strip().upper()
        if candidate in _VALID_LEVELS:
            root_level = candidate
        else:
            print(
                f"WARNING: {_ENV_ROOT}={raw_root!r} is not a valid level; ignoring.",
                file=sys.stderr,
            )

    return per_logger, root_level


def build_logging_config(
    installed_apps: list[str],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the `dictConfig`-shaped dict for `settings.LOGGING`.

    Merge order is documented at the module docstring and in
    `req-tap-logging-config-location-5`.
    """
    if env is None:
        env = os.environ

    loggers: dict[str, dict[str, Any]] = {}
    loggers.update(_first_party_logger_configs())
    loggers.update(_foundational_logger_configs())
    loggers.update(_app_logger_configs(installed_apps))
    loggers.update(plugin_logger_config(installed_apps))

    per_logger_overrides, root_override = _parse_env_overrides(env)
    for name, level in per_logger_overrides.items():
        if name in loggers:
            loggers[name] = {**loggers[name], "level": level}
        else:
            # Override mentions a logger we don't have a default for — create
            # an entry so the override takes effect. Inherits the standard
            # handler + no-propagate shape.
            loggers[name] = _logger_entry(level)

    root_entry: dict[str, Any] = {
        "level": root_override or "WARNING",
        "handlers": ["console"],
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "tap": {"format": _FORMAT, "datefmt": _DATEFMT},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "tap",
            },
        },
        "loggers": loggers,
        "root": root_entry,
    }
