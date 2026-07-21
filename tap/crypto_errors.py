"""Explain a low-level crypto failure that only happens under FIPS (doc-fips-assessment-record.md §5.3).

Under ``TAP_FIPS=1`` an OIDC login against an identity provider that signs its ``id_token`` with
a non-approved algorithm (JWS ``ES256K`` on secp256k1, or an RSA key below 2048 bits) fails
*before* ``jwt.decode`` — inside allauth's ``jwtkit.fetch_key → algorithm.from_jwk()`` — with a
``cryptography.exceptions.InternalError: Unknown OpenSSL error`` or a plain
``ValueError: Unable to sign/verify with this key``. Neither is a ``jwt.PyJWTError`` nor an
allauth error type, so the exception escapes BOTH allauth's callback handler and TAP's own
``RequestException`` rescue, surfacing as an uncaught HTTP 500 with no hint that FIPS is the
cause. The operator most exposed is one federating a non-FedRAMP IdP into a FedRAMP *staging*
environment — a scenario TAP must support.

This module turns such an exception into an actionable, human-readable string (or ``None`` if it
is not a recognizable FIPS crypto refusal). It is deliberately **Django-free and imports no
``tap_*`` app**, per CLAUDE.md's "push shared mechanics down; no tap_* interdependencies" rule —
so it lives in ``tap/`` and the auth middleware (``tap_auth``) composes it. It also does not
import ``cryptography``: it matches on the exception type *name* and message substrings, so a
plain ``ValueError`` in the chain is still recognized and the explainer adds no import coupling.

The message the error carries is generic ("Unknown OpenSSL error"), so we walk the whole
exception chain (``__cause__`` / ``__context__``) — the informative frame is usually a cause of
the outer exception, not the outer exception itself.
"""

from __future__ import annotations

from collections.abc import Iterator

#: The remediation appended to every explanation — the two ways out of a FIPS/algorithm clash.
_REMEDIATION = (
    "Configure the identity provider to sign its id_token with a FIPS-approved algorithm "
    "(RS256/PS256/ES256/ES384/EdDSA and RSA keys ≥ 2048 bits), or run this instance with "
    "TAP_FIPS=0."
)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield the exception and its ``__cause__`` / ``__context__`` chain, once each."""
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        stack.append(current.__cause__)
        stack.append(current.__context__)


def _classify(exc: BaseException) -> str | None:
    """Return a cause-specific explanation for a single exception, or ``None``."""
    name = type(exc).__name__
    message = str(exc)
    lowered = message.lower()

    # RSA key below the FIPS 2048-bit floor (cryptography raises a plain ValueError).
    if name == "ValueError" and "unable to sign/verify with this key" in lowered:
        return (
            "The identity provider's signing key is too small for FIPS mode " "(RSA keys must be at least 2048 bits)."
        )
    # Non-approved digest requested for security use (MD5) — the digital-envelope refusal.
    if "digital envelope routines" in lowered or "evp_generic_fetch" in lowered:
        return (
            "A non-approved hash algorithm (e.g. MD5) was requested for a security operation, "
            "which FIPS mode refuses."
        )
    # Non-approved curve (e.g. secp256k1 / JWS ES256K) — cryptography's generic InternalError.
    if name == "InternalError" and "openssl" in lowered:
        return (
            "The identity provider signed its id_token with an algorithm this FIPS-mode "
            "deployment cannot verify (for example ES256K on the secp256k1 curve)."
        )
    if name == "UnsupportedAlgorithm":
        return (
            "The identity provider used a cryptographic algorithm that is not available in this "
            "FIPS-mode deployment's active providers."
        )
    return None


def explain_crypto_error(exc: BaseException) -> str | None:
    """Return an actionable explanation if ``exc`` (or a cause in its chain) is a FIPS crypto
    refusal, else ``None``.

    The returned string is safe to show to an operator: it names the likely cause and the two
    remediations. ``None`` means "not a recognizable FIPS crypto error" — the caller should let
    the exception continue to its normal handling (a real 500), never swallow it.
    """
    for link in _chain(exc):
        explanation = _classify(link)
        if explanation is not None:
            return f"{explanation} {_REMEDIATION}"
    return None
