"""github_pat secret kind data schema + resolution helper.

`github_core` owns the `github_pat` data shape and validates it consumer-side
via tap_cares `require_secret_kind`. The bare kind name follows the
`aws_static_access_key` precedent — kind names describe the credential type,
not the owning plugin.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-secret).
"""

from __future__ import annotations

from typing import Any

from tap_cares.secrets import SecretRef, require_secret_kind, resolve_secret
from tap_cares.secrets.models import Secret

# The well-known SecretRef for the github_core collector. v0 has no per-
# instance config; the operator drops `github_core/collector.secret.json` under
# TAP_SECRETS_ROOT (no plugin config in core infra — operator-owned, off-grid).
# `scope` names the consuming plugin's slug, not the credential provider
# (req-tap-cares-secrets-consumer-scoping).
GITHUB_SECRET_REF = SecretRef(scope="github_core", key="collector")
GITHUB_SECRET_KIND = "github_pat"

# github_core owns this schema for the kind's `data` (req-github-core-secret-2).
# Strict: only the four v0 fields. Behavioral knobs beyond `initial_run_limit`
# were pruned in the spec's Pruned Knobs section; the schema enforces that
# pruning at load time.
GITHUB_PAT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["token", "repos"],
    "properties": {
        "token": {"type": "string", "minLength": 1},
        "api_base_url": {
            "type": "string",
            "minLength": 1,
            "default": "https://api.github.com",
        },
        "repos": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
                "pattern": r"^[^/]+/[^/]+$",
                "minLength": 3,
            },
        },
        "initial_run_limit": {
            "type": "integer",
            "minimum": 1,
            "default": 10,
        },
    },
}


class GithubCredentialError(Exception):
    """The github_pat secret is missing or otherwise unusable."""


def resolve_github_secret(ref: SecretRef = GITHUB_SECRET_REF) -> Secret:
    """Resolve and validate the github_pat collector secret.

    Raises `SecretNotFoundError` (missing) or `SecretValidationError`
    (wrong kind / bad `data` shape) from the secrets subsystem.
    """
    secret = resolve_secret(ref)
    require_secret_kind(secret, GITHUB_SECRET_KIND, data_schema=GITHUB_PAT_SCHEMA)
    return secret


def api_base_url(data: dict[str, Any]) -> str:
    """Return the API base URL with the documented default applied."""
    return data.get("api_base_url") or "https://api.github.com"


def initial_run_limit(data: dict[str, Any]) -> int:
    """Return the initial-run seed limit with the documented default applied."""
    return int(data.get("initial_run_limit") or 10)
