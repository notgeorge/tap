"""tap_cares secret registry.

req-tap-cares-secrets-registry (spec-tap-cares-secrets.md).

`secret_registry` is a `ScopedRegistry[Secret]` populated at Django startup
by `tap_cares.secrets.loader.load_secrets`. Consumer code should not touch
the registry directly — resolve secrets via `resolve_secret(ref)` so the
SecretRef boundary stays the single typed entry point
(req-tap-cares-secrets-registry-4).

Scope/key token format mirrors the collector registry's `_validate_collector_token`:
ASCII alphanumerics plus `_.-`, must start with an alphanumeric. The same
validator runs on register() and get() so malformed inputs fail loud at the
boundary instead of mid-lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from tap.registry import ScopedRegistry
from tap_cares.exceptions import (
    InvalidSecretRegistryKeyError,
    SecretNotFoundError,
)
from tap_cares.secrets.models import Secret, SecretLoadFailure, SecretRef

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


def _validate_secret_token(value: str) -> None:
    """Reject malformed scope or key tokens at the registry boundary."""
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise InvalidSecretRegistryKeyError(
            f"Invalid secret registry token {value!r}. Must match {_TOKEN_PATTERN.pattern}."
        )


secret_registry: ScopedRegistry[Secret] = ScopedRegistry(
    "secret",
    validate_key=_validate_secret_token,
    validate_scope=_validate_secret_token,
    title="Secret Registry",
    description="Scoped registry of tap_cares runtime secrets loaded from mounted files.",
)


@dataclass
class SecretLoadReport:
    """Process-wide record of the last `load_secrets` run's failures.

    Populated by the loader at startup (one load) and read by three consumers
    (the `tap_health` secrets probe, the `tap_cares` system check, and boot).
    A failed file degrades the instance rather than crash-looping startup; a
    failure whose file declared `required_for_boot: true` is *blocking* and
    escalates from degrade to fail-the-build / fail-health
    (req-tap-cares-secrets-resilient-load).
    """

    failures: list[SecretLoadFailure] = field(default_factory=list)

    def reset(self) -> None:
        """Clear recorded failures so a re-load starts from a clean slate."""
        self.failures.clear()

    @property
    def blocking(self) -> list[SecretLoadFailure]:
        """Failures that must block boot / fail the build (required_for_boot)."""
        return [f for f in self.failures if f.required_for_boot]

    @property
    def degraded(self) -> list[SecretLoadFailure]:
        """Failures that degrade the instance but do not block boot."""
        return [f for f in self.failures if not f.required_for_boot]


# Process-wide singleton. Tests pass an isolated report= to load_secrets so
# this is never mutated under test (mirrors the registry= convention).
secret_load_report = SecretLoadReport()


def resolve_secret(ref: SecretRef) -> Secret:
    """Return the registered Secret for `ref`.

    Raises:
        InvalidSecretRegistryKeyError: if `ref.scope` or `ref.key` is malformed.
        SecretNotFoundError: if no secret is registered for `scope:key`.
    """
    try:
        return secret_registry.get(ref.key, scope=ref.scope)
    except KeyError:
        raise SecretNotFoundError(
            f"No secret registered for {ref.qualified!r}. " f"Registered: {secret_registry.keys()}"
        ) from None
