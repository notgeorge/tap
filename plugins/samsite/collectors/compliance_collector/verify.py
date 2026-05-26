"""Sigstore signature verification for the samsite compliance collector.

Each fetched artifact carries a Sigstore bundle (the workflow signed it via
cosign keyless + GitHub OIDC). Verification asserts: signature valid; cert
chains to the public Fulcio roots; Rekor inclusion proof valid; cert identity
matches the policy (issued by GitHub Actions OIDC, to a workflow in the
expected repository). The collector records the verification result as typed
fields on the resulting node (signature_verified, signed_by, rekor_log_index,
verified_at). A failed verification records `signature_verified=False` but
does not abort the run — the artifact still collects, flagged (per
req-samsite-collector-verify).

Requires the live signature bundles to be the standardized Sigstore bundle
format (cosign `--new-bundle-format`); the legacy `{base64Signature, cert,
rekorBundle}` cosign bundle format is not parseable by sigstore-python.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import cryptography.x509 as x509
from sigstore.models import Bundle, InvalidBundle
from sigstore.verify import Verifier, policy


@lru_cache(maxsize=1)
def _get_verifier() -> Verifier:
    """Cache the production Verifier — fetching the TUF trust root is heavy.

    One verifier per worker lifetime is plenty; verification policies are
    per-call, not baked into the Verifier.
    """
    return Verifier.production()


def _signed_by_from_cert(bundle: Bundle) -> str:
    """Extract the signing cert's SAN URI — the workflow identity that signed."""
    cert = bundle.signing_certificate
    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return ""
    for name in san_ext:
        if isinstance(name, x509.UniformResourceIdentifier):
            return name.value
    return ""


def verify_artifact(
    body: bytes,
    bundle_bytes: bytes,
    *,
    oidc_issuer: str,
    github_repository: str,
) -> dict[str, Any]:
    """Verify an artifact against its Sigstore bundle under the given policy.

    Returns a dict shaped for the verification fields on a fedramp_20x_ksi
    compliance-artifact node: ``signature_verified`` (True / False / None),
    ``signed_by`` (cert SAN URI), ``rekor_log_index`` (best-effort), and
    ``verified_at`` (ISO 8601 UTC).
    """
    verified_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    result: dict[str, Any] = {
        "signature_verified": None,
        "signed_by": "",
        "rekor_log_index": "",
        "verified_at": verified_at,
    }

    # Parse the bundle. An unparseable bundle is `signature_verified=None` —
    # unknown rather than failed (we can't even confirm a signature exists).
    try:
        bundle = Bundle.from_json(bundle_bytes)
    except (InvalidBundle, ValueError, KeyError):
        return result

    result["signed_by"] = _signed_by_from_cert(bundle)

    pol = policy.AllOf(
        [
            policy.OIDCIssuer(oidc_issuer),
            policy.GitHubWorkflowRepository(github_repository),
        ]
    )

    try:
        _get_verifier().verify_artifact(body, bundle=bundle, policy=pol)
    except Exception:
        # sigstore raises VerificationError / its subclasses on policy or
        # cryptographic failure; broad catch keeps any unexpected lib error
        # from aborting the run — the verdict is "False (visible)".
        result["signature_verified"] = False
        return result

    result["signature_verified"] = True
    return result
