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

from urllib.parse import urlsplit

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


def _origin_of(url: str) -> str:
    """Reduce a URL to its origin (scheme + host + port), lowercased.

    The unit WebAuthn actually compares. A base URL carrying a path, a trailing
    slash, or mixed case must still be judged on its origin alone.
    """
    parts = urlsplit(url.strip())
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def enrollment_base_url() -> str:
    """The base URL an enrollment link MUST use: exactly the ceremony's origin.

    Derived from :func:`expected_origins` rather than re-reading settings, so the
    link a human clicks and the origin the ceremony will accept cannot drift —
    they are the same value by construction, not by two parallel derivations.

    Deliberately strict, with no fallback chain. The two enrollment commands
    previously each derived their own base URL as
    ``TAP_PASSKEY_ORIGIN or TAP_BASE_URL or "http://localhost:8000"``, but every
    branch of that chain past the first is *guaranteed* to mint a dead link:
    those branches can only run when ``TAP_PASSKEY_ORIGIN`` is unset, and an
    unset origin is exactly what makes :func:`expected_origins` raise. The
    fallbacks converted a clear "set TAP_PASSKEY_ORIGIN" into a link that looks
    fine, gets clicked, and fails confusingly at the WebAuthn step (2026-08
    code-clone sweep, finding S2).

    Raises:
        ImproperlyConfigured: ``TAP_PASSKEY_ORIGIN`` is not set — via
            :func:`expected_origins`, with its actionable message.
    """
    return expected_origins()[0]


def assert_enrollment_origin(base_url: str) -> None:
    """Refuse an operator-supplied enrollment base URL that the ceremony will reject.

    ``--base-url`` stays available as the explicit override (proxies, port
    forwards), but a value whose origin differs from ``TAP_PASSKEY_ORIGIN``
    produces a link that CANNOT complete: the browser would present the other
    origin and the ceremony compares exactly. Refusing at mint time is honest —
    a warning would ship the same dead link with extra text.

    Raises:
        ImproperlyConfigured: The origin does not match the configured one (or
            no origin is configured at all).
    """
    expected = expected_origins()[0]
    if _origin_of(base_url) != _origin_of(expected):
        raise ImproperlyConfigured(
            f"--base-url origin {_origin_of(base_url)!r} does not match TAP_PASSKEY_ORIGIN "
            f"{_origin_of(expected)!r}. The passkey ceremony compares the origin exactly, so a link "
            f"minted at a different origin cannot complete. Set TAP_PASSKEY_ORIGIN to the origin the "
            f"browser will actually be on, or pass a --base-url on that origin."
        )
