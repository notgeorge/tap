"""Passkey (WebAuthn) RP configuration (req-tap-auth-passkey-webauthn-5/7).

RP-ID (the registrable domain a credential is scoped to) and the expected origin
are read from settings/env (``TAP_PASSKEY_*``). The expected origin is **exact** —
scheme + host + port — never a wildcard or any-``localhost``: a wildcard would let
a co-resident ``localhost:<other>`` service relay a TAP-challenge assertion back to
TAP (req-tap-auth-passkey-webauthn-7). In the MVP these come from settings/env, not
the boot method block (that is a Phase-1b artifact).

**Pinning warning:** changing RP-ID after credentials exist invalidates every
registered passkey (req-tap-auth-passkey-webauthn-5). Set it deliberately at genesis.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def rp_id() -> str:
    """The pinned Relying Party ID (registrable domain). Dev uses ``localhost``."""
    rp = (getattr(settings, "TAP_PASSKEY_RP_ID", "") or "").strip()
    if not rp:
        raise ImproperlyConfigured("TAP_PASSKEY_RP_ID is not set; the passkey method requires a pinned RP-ID.")
    return rp


def rp_name() -> str:
    """Human-facing RP name shown by the authenticator UI."""
    return (getattr(settings, "TAP_PASSKEY_RP_NAME", "") or "TAP").strip() or "TAP"


def expected_origins() -> list[str]:
    """The exact allowed origin(s) (scheme+host+port). Fail closed if unset — an
    empty/absent origin must NOT degrade to an any-origin match."""
    origin = (getattr(settings, "TAP_PASSKEY_ORIGIN", "") or "").strip()
    if not origin:
        raise ImproperlyConfigured(
            "TAP_PASSKEY_ORIGIN is not set; the passkey ceremony requires an EXACT expected origin "
            "(scheme+host+port). No wildcard / any-origin / any-localhost is permitted "
            "(req-tap-auth-passkey-webauthn-7)."
        )
    return [origin]
