"""Provider interface, config model, and self-test result types (req-tap-auth-providers).

A provider implementation is a small object exposing four operations:

    validate_config(config)            -> list[SelfTestResult]   (offline shape checks)
    resolve_secrets(config)            -> dict[str, str]         (secret material, in memory)
    self_test(config, secrets, live=)  -> list[SelfTestResult]   (offline + optional live)
    build_allauth_settings(config, secrets) -> dict              (one allauth APPS entry)

Self-tests are a first-class investment (req-tap-auth-providers): IdPs break the
same way collector upstreams do (credential rotation, discovery-document drift,
tenant/domain changes), and a standard, code-free probe surface lets an operator
(or the future healer) ask "what is wrong with auth right now" the same way the
CollectorBase self-tests do. Results carry a status, a human message, and a docs
link; checks are split into offline (shape/secret-presence/local derivations)
and live (network/IdP reachability) phases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ProviderError(Exception):
    """A provider operation failed in a way that is not a self-test result —
    e.g. a secret cannot be resolved at all, or config is structurally unusable
    for building settings. Self-tests REPORT problems; this is raised when an
    operation cannot proceed."""


class SelfTestStatus(StrEnum):
    """Outcome of a single self-test check (req-tap-auth-providers)."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class SelfTestPhase(StrEnum):
    """Which phase a check belongs to. OFFLINE = shape/secret/local derivation
    (no network); LIVE = network/IdP reachability (req-tap-auth-providers-5)."""

    OFFLINE = "offline"
    LIVE = "live"


@dataclass(frozen=True)
class SelfTestResult:
    """One self-test check outcome."""

    check: str
    status: SelfTestStatus
    phase: SelfTestPhase
    message: str
    docs_url: str | None = None

    @property
    def ok(self) -> bool:
        """True when this check does not block boot (pass/warn/skip). FAIL is
        the only blocking status (req-tap-auth-providers: boot fails on any
        provider `fail`; `warn` continues with clear logs)."""
        return self.status is not SelfTestStatus.FAIL


@dataclass(frozen=True)
class ProviderConfig:
    """A single provider entry from the boot auth config (req-tap-auth-providers).

    Common fields are explicit; provider-type-specific settings (e.g. a
    google_oidc provider's ``allowed_domains``) live in ``config`` and are
    interpreted by the concrete provider. ``secret`` is the *key* of the
    ``auth``-scoped ``*.secret.json`` holding the client credentials — a
    reference, never the secret value (req-tap-auth-providers-3). It defaults to
    the provider ``id`` (the convention: secret basename == provider id).
    """

    id: str
    type: str
    display_name: str
    secret: str = ""
    critical_for_boot: bool = True
    auto_provision: bool = True
    config: Mapping[str, Any] = field(default_factory=dict)

    @property
    def secret_key(self) -> str:
        """The secret key to resolve (defaults to the provider id)."""
        return self.secret or self.id

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProviderConfig:
        """Build a ProviderConfig from a boot-config dict. Raises ProviderError
        on a missing required field (id/type/display_name) so a malformed static
        config fails loudly rather than silently producing a half-built provider."""
        missing = [k for k in ("id", "type", "display_name") if not raw.get(k)]
        if missing:
            raise ProviderError(f"provider config missing required field(s): {', '.join(missing)}")
        known = {"id", "type", "display_name", "secret", "critical_for_boot", "auto_provision"}
        return cls(
            id=str(raw["id"]),
            type=str(raw["type"]),
            display_name=str(raw["display_name"]),
            secret=str(raw.get("secret", "")),
            critical_for_boot=bool(raw.get("critical_for_boot", True)),
            auto_provision=bool(raw.get("auto_provision", True)),
            config={k: v for k, v in raw.items() if k not in known},
        )


class Provider(Protocol):
    """The common provider interface (req-tap-auth-providers-4). A concrete
    provider is a stateless object; all state arrives via ``config``/``secrets``."""

    type: str

    def validate_config(self, config: ProviderConfig) -> list[SelfTestResult]:
        """Offline structural validation of a provider config (no network, no
        secrets). Returns one result per check."""
        ...

    def resolve_secrets(self, config: ProviderConfig) -> dict[str, str]:
        """Resolve the provider's secret material into memory (never persisted).
        Raises ProviderError if the secret cannot be resolved/validated."""
        ...

    def self_test(self, config: ProviderConfig, secrets: Mapping[str, str], *, live: bool) -> list[SelfTestResult]:
        """Run offline checks always; when ``live`` is True also run network/IdP
        reachability checks. Never raises for an expected failure — returns a
        FAIL result instead."""
        ...

    def build_allauth_settings(self, config: ProviderConfig, secrets: Mapping[str, str]) -> dict[str, Any]:
        """Build the allauth provider ``APPS`` entry for this provider."""
        ...
