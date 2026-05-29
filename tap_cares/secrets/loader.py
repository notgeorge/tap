"""Startup-time `*.secret.json` loader.

req-tap-cares-secrets-files, req-tap-cares-secrets-shape
(spec-tap-cares-secrets.md).

`load_secrets(root, *, registry=...)` recursively scans `root` for files
whose basename matches `<key>.secret.json`, parses each one, and registers
the resulting `Secret` in the supplied registry. Directories are
non-semantic — they exist only for operator organization. Dotfiles and
non-matching suffixes are ignored.

#### Failure modes

- **Missing or empty root** → silent no-op. TAP installs without runtime
  secrets are normal; capability runs that need a missing secret fail at
  run time via `resolve_secret`, not at startup
  (req-tap-cares-secrets-redaction-3).

- **Malformed JSON, missing required field, basename ≠ JSON key** →
  `SecretLoadError`. These are configuration errors and must be fixed
  before any run. Fail loud at startup.

- **Duplicate `scope:key` across two files** → `SecretDuplicateError`,
  even when the duplicates appear in different directories
  (req-tap-cares-secrets-files-6).

Tests pass a `tmp_path`-backed `registry=` argument so the production
`secret_registry` is never touched.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tap_cares.exceptions import (
    InvalidSecretRegistryKeyError,
    SecretDuplicateError,
    SecretLoadError,
)
from tap_cares.secrets.models import Secret, SecretRef, freeze_mapping
from tap_cares.secrets.registry import secret_registry
from tap_grid.registry import ScopedRegistry

logger = logging.getLogger(__name__)

SECRET_SUFFIX = ".secret.json"

_REQUIRED_FIELDS = ("scope", "key", "kind", "description", "data")


def load_secrets(
    root: Path | str | None,
    *,
    registry: ScopedRegistry[Secret] | None = None,
) -> list[SecretRef]:
    """Scan `root` and register every `<key>.secret.json` file found.

    Args:
        root: Directory to scan. If None, missing, or not a directory, the
            loader logs and returns an empty list — TAP starts normally.
        registry: Target registry. Defaults to the process-wide
            `secret_registry`; tests pass an isolated instance.

    Returns:
        The list of SecretRefs registered, in the order they were loaded.
        Useful for diagnostics and for tests that want to assert "exactly
        these refs are now registered".

    Raises:
        SecretLoadError / SecretDuplicateError / InvalidSecretRegistryKeyError:
            on any structural problem. Loading is fail-fast: a single bad
            file aborts startup so an operator notices before any capability
            runs against partial state.
    """
    target = registry if registry is not None else secret_registry

    if root is None:
        logger.info("[f769] tap-cares secrets: no root configured; skipping load.")
        return []

    root_path = Path(root)
    if not root_path.exists():
        logger.info("[eb76] tap-cares secrets: root %s does not exist; skipping load.", root_path)
        return []
    if not root_path.is_dir():
        raise SecretLoadError(f"tap-cares secrets root {root_path!s} exists but is not a directory.")

    loaded: list[SecretRef] = []
    # rglob is deterministic across platforms when fed a sorted iterator.
    for path in sorted(root_path.rglob(f"*{SECRET_SUFFIX}")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        secret = _load_secret_file(path)
        try:
            target.register(secret.ref.key, secret, scope=secret.ref.scope)
        except InvalidSecretRegistryKeyError:
            raise
        except Exception as exc:
            # ScopedRegistry raises ImproperlyConfigured on duplicate keys.
            # Translate to the spec-named exception so callers can catch it
            # without depending on Django internals.
            raise SecretDuplicateError(f"Duplicate secret {secret.ref.qualified!r} loaded from {path}: {exc}") from None
        loaded.append(secret.ref)

    logger.info(
        "[d644] tap-cares secrets: loaded %d secret(s) from %s: %s.",
        len(loaded),
        root_path,
        ", ".join(sorted(ref.qualified for ref in loaded)) or "(none)",
    )
    return loaded


def _load_secret_file(path: Path) -> Secret:
    """Parse `path` and return a Secret. Raises SecretLoadError on any problem."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecretLoadError(f"Failed to read secret file {path}: {exc}") from None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SecretLoadError(f"Secret file {path} is not valid JSON: line {exc.lineno} col {exc.colno}") from None

    if not isinstance(payload, dict):
        raise SecretLoadError(f"Secret file {path} must contain a JSON object, got {type(payload).__name__}.")

    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        raise SecretLoadError(f"Secret file {path} is missing required field(s): {missing}.")

    scope = payload["scope"]
    key = payload["key"]
    kind = payload["kind"]
    description = payload["description"]
    data = payload["data"]
    metadata = payload.get("metadata", {})

    if not isinstance(scope, str) or not isinstance(key, str):
        raise SecretLoadError(f"Secret file {path}: scope and key must be strings.")
    if not isinstance(kind, str) or not kind:
        raise SecretLoadError(f"Secret file {path}: kind must be a non-empty string.")
    if not isinstance(description, str) or not description.strip():
        raise SecretLoadError(f"Secret file {path}: description must be a non-empty string.")
    if not isinstance(data, dict):
        raise SecretLoadError(f"Secret file {path}: data must be a JSON object.")
    if not isinstance(metadata, dict):
        raise SecretLoadError(f"Secret file {path}: metadata must be a JSON object when present.")

    _check_basename_matches_key(path, key)

    return Secret(
        ref=SecretRef(scope=scope, key=key),
        kind=kind,
        description=description,
        data=freeze_mapping(data),
        metadata=freeze_mapping(metadata),
        source_path=path,
    )


def _check_basename_matches_key(path: Path, key: str) -> None:
    """Enforce req-tap-cares-secrets-files-5: basename `<key>` matches JSON `key`."""
    name = path.name
    if not name.endswith(SECRET_SUFFIX):
        # rglob filter guarantees this, but keep the guard for explicit callers.
        raise SecretLoadError(f"Secret file {path} does not end with {SECRET_SUFFIX}.")
    basename_key = name[: -len(SECRET_SUFFIX)]
    if basename_key != key:
        raise SecretLoadError(
            f"Secret file {path} basename key {basename_key!r} does not match " f"JSON 'key' field {key!r}."
        )


__all__: list[Any] = ["load_secrets", "SECRET_SUFFIX"]
