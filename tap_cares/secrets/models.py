"""SecretRef and Secret value objects.

req-tap-cares-secrets-registry (spec-tap-cares-secrets.md).

SecretRef is the stable, non-secret reference shape passed through runtime
code. Secret is the rich runtime value resolved through the registry; it
carries identity, kind, description, the actual data payload, optional
operator metadata, and the source path the value was loaded from.

Both are frozen dataclasses. Secret's __repr__ deliberately omits `data` and
`metadata` so accidental logging or tracebacks cannot leak secret material.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class SecretRef:
    """Non-secret reference to a runtime secret.

    Passed through capability code as a typed alternative to raw
    `scope:key` strings (req-tap-cares-secrets-registry-3).
    """

    scope: str
    key: str

    @property
    def qualified(self) -> str:
        """The fully-qualified `scope:key` string used for registry lookup."""
        return f"{self.scope}:{self.key}"

    def __str__(self) -> str:
        return self.qualified


@dataclass(frozen=True)
class Secret:
    """Resolved runtime secret.

    Carries the data payload alongside enough non-secret context for
    diagnostics and consumer validation. Construct via the loader; do not
    instantiate inline in capability code. Resolve via `resolve_secret(ref)`.

    The __repr__ omits `data` and `metadata` so a Secret accidentally
    interpolated into a log line or traceback does not leak material.
    """

    ref: SecretRef
    kind: str
    description: str
    data: Mapping[str, Any]
    metadata: Mapping[str, Any]
    source_path: Path

    def __repr__(self) -> str:
        return f"Secret(ref={self.ref.qualified!r}, kind={self.kind!r}, source={self.source_path})"


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only view of `value` for storage on a Secret."""
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class SecretLoadFailure:
    """A single secret file that failed to load at startup.

    Carries only non-secret context — the source path, the qualified
    ``scope:key`` when determinable, a redacted structural reason, and the
    file's ``required_for_boot`` flag. The loader records these instead of
    raising so a malformed file degrades the instance rather than crash-looping
    startup (req-tap-cares-secrets-resilient-load). Readers: the ``tap_health``
    secrets probe, the ``tap_cares`` system check, and boot.
    """

    path: str
    reason: str
    required_for_boot: bool
    qualified: str | None = None
