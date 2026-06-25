"""Provider-specific login machinery (req-tap-auth-providers).

Each external IdP type lives under ``tap_auth/providers/`` behind a common
interface (``validate_config`` / ``resolve_secrets`` / ``self_test`` /
``build_allauth_settings``). The host (boot, the self-test command, the
allauth-settings wiring) talks to providers only through this interface, so a
new provider type is a new module here and nothing else changes.

This package is deliberately free of Django *model* imports so it is safe to
import at settings-build time (the allauth-settings wiring runs there). It uses
only stdlib, jsonschema, and Django settings/conf.
"""

from tap_auth.providers.base import (
    AccessDecision,
    ProviderConfig,
    ProviderError,
    SelfTestPhase,
    SelfTestResult,
    SelfTestStatus,
)
from tap_auth.providers.registry import UnknownProviderType, get_provider, provider_types
from tap_auth.providers.wiring import (
    build_socialaccount_providers,
    get_provider_config,
    iter_provider_configs,
)

__all__ = [
    "AccessDecision",
    "ProviderConfig",
    "ProviderError",
    "SelfTestPhase",
    "SelfTestResult",
    "SelfTestStatus",
    "UnknownProviderType",
    "build_socialaccount_providers",
    "get_provider",
    "get_provider_config",
    "iter_provider_configs",
    "provider_types",
]
