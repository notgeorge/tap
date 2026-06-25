"""Build allauth's SOCIALACCOUNT_PROVIDERS from TAP provider configs.

This is the bridge between TAP's declarative provider config and allauth. It runs
at settings-build time (so allauth sees the providers from first request) and is
also used by boot's provider-validation phase (req-tap-auth-boot). Secrets are
resolved into memory here and embedded in the allauth APPS list — which lives in
*settings*, never the DB (req-tap-auth-providers-3: allauth's SocialApp DB row
would persist the secret; the settings APPS path keeps it in memory only).

``build_socialaccount_providers`` is intentionally tolerant of resolution
failures at settings-build time when ``critical_for_boot`` is False: a provider
whose live IdP is unavailable should not prevent the process from importing
settings (req-tap-auth-providers-6). A *malformed* static config or a missing
secret on a ``critical_for_boot`` provider raises — that is a deploy-time error
the boot phase surfaces loudly. The richer offline/live self-test gating belongs
to the boot phase (increment 4); this function only does enough to assemble
allauth settings.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from tap_auth.providers.base import ProviderConfig, ProviderError
from tap_auth.providers.registry import UnknownProviderType, get_provider

logger = logging.getLogger(__name__)

# allauth provider key for the OIDC engine every google_oidc provider rides on.
_OPENID_CONNECT = "openid_connect"


def build_socialaccount_providers(
    raw_configs: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a SOCIALACCOUNT_PROVIDERS dict for the given provider configs.

    Each config is parsed, its provider implementation resolved, its secret
    resolved, and its allauth APPS entry built. The result groups all
    openid_connect apps under the ``openid_connect`` key, e.g.::

        {"openid_connect": {"APPS": [ {provider_id, name, client_id, ...}, ... ]}}

    Empty input → empty dict (no providers configured; local auth only).
    """
    apps: list[dict[str, Any]] = []
    for raw in raw_configs:
        config = ProviderConfig.from_dict(raw)
        try:
            provider = get_provider(config.type)
        except UnknownProviderType:
            # Unknown types fail immediately (req-tap-auth-providers).
            raise
        try:
            secrets = provider.resolve_secrets(config)
            entry = provider.build_allauth_settings(config, secrets)
        except ProviderError:
            if config.critical_for_boot:
                # A critical provider that cannot be assembled is a hard error.
                raise
            # Non-critical: log loudly and skip — login via this provider is
            # unavailable, but the process still starts (req-tap-auth-providers-6).
            logger.warning(
                "[9c88] non-critical provider %s could not be assembled; login unavailable",
                config.id,
            )
            continue
        apps.append(entry)

    if not apps:
        return {}
    return {_OPENID_CONNECT: {"APPS": apps}}
