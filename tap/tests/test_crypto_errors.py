"""Unit tests for tap.crypto_errors.explain_crypto_error (req-tap-auth-google-oidc-fips-algorithm).

Pure function over synthetic exceptions — no FIPS build needed. Verifies each recognizable
FIPS crypto-refusal signature from doc-fips-assessment-record.md §5.3 is classified, that the
exception chain is walked (the informative frame is usually a __cause__, not the outer error),
and that an unrelated exception returns None so the caller lets it stay a real 500.
"""

from __future__ import annotations

import pytest

from tap.crypto_errors import explain_crypto_error


# Stand-ins named EXACTLY as cryptography names them — _classify matches on type(exc).__name__,
# so the local class names must be faithful to the real cryptography.exceptions types.
class InternalError(Exception):
    """Stand-in for cryptography.exceptions.InternalError (matched by type name)."""


class UnsupportedAlgorithm(Exception):
    """Stand-in for cryptography.exceptions.UnsupportedAlgorithm (matched by type name)."""


@pytest.mark.parametrize(
    ("exc", "needle"),
    [
        (ValueError("Unable to sign/verify with this key"), "at least 2048 bits"),
        (InternalError("Unknown OpenSSL error"), "es256k"),
        (ValueError("[digital envelope routines] unsupported"), "md5"),
        (UnsupportedAlgorithm("no such alg"), "not available"),
    ],
)
def test_recognized_signatures_are_explained(exc: Exception, needle: str) -> None:
    explanation = explain_crypto_error(exc)
    assert explanation is not None
    assert needle in explanation.lower()
    # Every explanation carries the remediation (configure the IdP, or TAP_FIPS=0).
    assert "tap_fips=0" in explanation.lower()


def test_unrelated_exception_returns_none() -> None:
    assert explain_crypto_error(ValueError("a totally ordinary bug")) is None
    assert explain_crypto_error(KeyError("missing")) is None


def test_walks_the_cause_chain() -> None:
    """The generic outer error carries no signal; the cause does."""
    try:
        try:
            raise ValueError("Unable to sign/verify with this key")
        except ValueError as inner:
            raise RuntimeError("login failed") from inner
    except RuntimeError as outer:
        assert explain_crypto_error(outer) is not None


def test_walks_the_context_chain() -> None:
    """A non-`raise from` (implicit __context__) chain is walked too."""
    try:
        try:
            raise InternalError("Unknown OpenSSL error")
        except InternalError:
            raise RuntimeError("wrapper")  # noqa: B904 - deliberately implicit __context__
    except RuntimeError as outer:
        assert explain_crypto_error(outer) is not None


def test_cycle_in_chain_terminates() -> None:
    """A self-referential exception chain must not loop forever."""
    exc = ValueError("ordinary")
    exc.__cause__ = exc  # pathological, but the walker must terminate
    assert explain_crypto_error(exc) is None
