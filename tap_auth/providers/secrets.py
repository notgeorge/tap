"""Resolve auth provider secrets from the mounted ``*.secret.json`` store.

Provider client credentials live in the same ``*.secret.json`` files as the rest
of TAP's runtime secrets (one shared, gitignored, bind-mounted store), under the
``auth`` scope. tap_auth reads its own provider secrets directly here rather than
through the tap-cares registry, because allauth settings are built at
settings-import time — before ``tap_cares.ready()`` loads that registry. The file
format is the established tap-cares envelope; tap_auth owns the ``oidc_client``
data-block schema (``tap_auth/schemas/oidc_client_secret.schema.json``) and
validates against it here.

Secret material is returned in memory only and never logged in full
(req-tap-auth-providers-3 / the threat model in req-tap-auth-capabilities).
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings
from jsonschema import Draft202012Validator

from tap_auth.providers.base import ProviderError

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "oidc_client_secret.schema.json"


@functools.lru_cache(maxsize=1)
def _oidc_client_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text())
    return Draft202012Validator(schema)


def _secrets_root() -> Path:
    # Prefer the live settings (so test fixtures overriding TAP_SECRETS_ROOT
    # work), but fall back to os.environ when settings is not yet configured —
    # build_socialaccount_providers runs DURING tap.settings import, where the
    # lazy django.conf.settings object is mid-initialization and its attributes
    # are not reliably accessible. os.environ is the same source settings.py reads.
    root: str | None = None
    if settings.configured:
        root = getattr(settings, "TAP_SECRETS_ROOT", None)
    if not root:
        root = os.environ.get("TAP_SECRETS_ROOT")
    if not root:
        raise ProviderError("TAP_SECRETS_ROOT is not configured; cannot resolve provider secrets")
    return Path(root)


def _find_secret_file(scope: str, key: str) -> Path:
    """Locate the ``<key>.secret.json`` whose envelope declares ``scope``/``key``.

    Directories under the root are organizational only (spec-tap-cares-secrets),
    so we match on the basename then confirm the declared scope/key inside.
    """
    root = _secrets_root()
    if not root.is_dir():
        raise ProviderError(f"secrets root {root} does not exist; cannot resolve {scope}:{key}")
    for path in sorted(root.rglob(f"{key}.secret.json")):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"secret file {path} is unreadable/invalid JSON: {exc}") from exc
        if doc.get("scope") == scope and doc.get("key") == key:
            return path
    raise ProviderError(
        f"no secret file found for {scope}:{key} under {root} "
        f"(expected a '{key}.secret.json' with scope='{scope}', key='{key}')"
    )


def resolve_oidc_client_secret(key: str, *, scope: str = "auth") -> dict[str, str]:
    """Return ``{'client_id': ..., 'client_secret': ...}`` for an OIDC provider.

    Validates the whole secret file against the ``oidc_client`` schema (so a
    malformed secret fails loud and specific, not as a mystery login error) and
    returns only the ``data`` block.
    """
    path = _find_secret_file(scope, key)
    doc: dict[str, Any] = json.loads(path.read_text())
    errors = sorted(_oidc_client_validator().iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{list(e.path) or '<root>'}: {e.message}" for e in errors)
        raise ProviderError(f"secret {scope}:{key} ({path.name}) failed oidc_client schema: {detail}")
    data = doc["data"]
    return {"client_id": str(data["client_id"]), "client_secret": str(data["client_secret"])}


def secret_exists(key: str, *, scope: str = "auth") -> bool:
    """True if a resolvable secret file exists for ``scope:key`` (no validation)."""
    try:
        _find_secret_file(scope, key)
    except ProviderError:
        return False
    return True
