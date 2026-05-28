"""Canonical TAP-side Sigstore bundle verification.

Every TAP plugin that verifies a Sigstore signature bundle calls
``verify_bundle`` here. The function wraps ``sigstore-python`` so the
upstream API is contained in this single module: consumer plugins import
only from ``sigstore_core.*`` and never from ``sigstore.*`` directly.

Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md
(req-sigstore-core-verify, req-sigstore-core-policy, req-sigstore-core-disclosure).

v0 supports Sigstore bundles whose verification rests on a Rekor
transparency-log inclusion proof. RFC3161 timestamp-only bundles are
rejected with ``failure_code="no_rekor_proof"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import cryptography.x509 as x509
from sigstore.models import Bundle, InvalidBundle
from sigstore.verify import Verifier, policy as sigstore_policy

# Public Fulcio + Rekor identifiers. v0 only encounters the public-good
# instances; the model layer accommodates others without code change.
PUBLIC_GOOD_FULCIO_URL = "https://fulcio.sigstore.dev"
PUBLIC_GOOD_FULCIO_NAME = "Sigstore Public Good Fulcio"
PUBLIC_GOOD_REKOR_URL = "https://rekor.sigstore.dev"
TUF_PUBLIC_GOOD_SOURCE = "tuf-public-good"


@dataclass(frozen=True)
class GitHubWorkflowPolicy:
    """Verification policy for GitHub Actions-signed bundles.

    ``oidc_issuer`` and ``github_repository`` are required (repo-level
    binding is the weakest useful identity check). The optional fields
    tighten the check; the applied predicates are recorded on the
    ATTESTED_BY edge so the verdict is interpretable later.

    Spec: req-sigstore-core-policy-2.
    """

    oidc_issuer: str
    github_repository: str
    workflow_identity_uri: str | None = None
    workflow_ref: str | None = None
    workflow_sha: str | None = None


# Union alias for future policy descriptors (EmailIdentityPolicy,
# GitLabWorkflowPolicy, etc.). v0 ships exactly one concrete policy.
VerificationPolicy = GitHubWorkflowPolicy


@dataclass
class VerificationResult:
    """Structured outcome of a ``verify_bundle`` call.

    Spec: req-sigstore-core-verify, req-sigstore-core-verify-2,
    req-sigstore-core-verify-4.

    ``signature_verified`` is three-state:
      * ``True``  — signature, cert chain, Rekor inclusion proof, and policy all matched.
      * ``False`` — bundle parsed but some check failed; ``failure_code`` names the mode.
      * ``None``  — bundle could not be parsed at all; only ``failure_code`` and ``failure_detail`` are populated.
    """

    signature_verified: bool | None
    signed_by: str = ""
    signing_issuer: str = ""
    log_key_id: str = ""
    rekor_log_url: str = ""
    rekor_log_index: str = ""
    integrated_time: str = ""
    entry_kind: str = ""
    verified_at: str = ""
    failure_code: str = ""
    failure_detail: str = ""
    # The parsed bundle is opaque to consumers; it's passed back to
    # ``decompose.bundle_to_grift_fragment`` to avoid double-parsing. Not
    # part of any serialized representation.
    parsed_bundle: Bundle | None = field(default=None, repr=False)


@lru_cache(maxsize=1)
def _get_verifier() -> Verifier:
    """Cache the production Verifier — fetching the TUF trust root is heavy.

    Spec: req-sigstore-core-verify-6.
    """
    return Verifier.production()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def _signing_issuer_from_cert(bundle: Bundle) -> str:
    """Extract the OIDC issuer URL from the signing cert when present.

    Fulcio puts the OIDC issuer in a custom extension OID 1.3.6.1.4.1.57264.1.1
    (legacy) or OID 1.3.6.1.4.1.57264.1.8 (RFC8693 issuer URI). v0 best-effort
    reads either; absence is non-fatal.
    """
    cert = bundle.signing_certificate
    for oid_str in ("1.3.6.1.4.1.57264.1.8", "1.3.6.1.4.1.57264.1.1"):
        try:
            ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(oid_str)).value
        except x509.ExtensionNotFound:
            continue
        raw: Any = ext.value if hasattr(ext, "value") else ext
        if isinstance(raw, bytes):
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
        if isinstance(raw, str):
            return raw
    return ""


def _extract_log_data(bundle: Bundle) -> tuple[str, str, str, str]:
    """Best-effort extraction of (log_key_id, log_index, integrated_time, entry_kind).

    The Rekor inclusion proof lives inside the bundle's
    ``verification_material``. Field names track ``sigstore-python``'s
    parsed bundle shape but are wrapped in try/except so future upstream
    shape shifts degrade to empty strings instead of raising.
    """
    log_key_id = ""
    log_index = ""
    integrated_time = ""
    entry_kind = ""

    try:
        tlog_entries = bundle.log_entry
        # ``log_entry`` is a single TransparencyLogEntry on current
        # sigstore-python; older shapes used a list. Normalize.
        entries = tlog_entries if isinstance(tlog_entries, list) else [tlog_entries]
        if entries:
            first = entries[0]
            log_index_val = getattr(first, "log_index", None)
            if log_index_val is not None:
                log_index = str(log_index_val)
            integrated_val = getattr(first, "integrated_time", None)
            if integrated_val is not None:
                # integrated_time on sigstore-python is typically an int (seconds-since-epoch)
                # or already an ISO string. Normalize to ISO.
                if isinstance(integrated_val, int | float):
                    integrated_time = datetime.fromtimestamp(int(integrated_val), tz=UTC).isoformat().replace("+00:00", "Z")
                else:
                    integrated_time = str(integrated_val)
            log_id_obj = getattr(first, "log_id", None)
            if log_id_obj is not None:
                key_id = getattr(log_id_obj, "key_id", None) or log_id_obj
                if isinstance(key_id, bytes):
                    log_key_id = key_id.hex()
                else:
                    log_key_id = str(key_id)
            kind_val = getattr(first, "kind_version", None) or getattr(first, "kind", None)
            if kind_val is not None:
                entry_kind = getattr(kind_val, "kind", None) or str(kind_val)
    except (AttributeError, IndexError, ValueError, TypeError):
        pass

    return log_key_id, log_index, integrated_time, entry_kind


def _translate_policy(p: GitHubWorkflowPolicy) -> sigstore_policy.VerificationPolicy:
    """Convert a TAP-side policy descriptor into the equivalent sigstore-python policy.

    Spec: req-sigstore-core-policy-1, req-sigstore-core-policy-2.
    """
    predicates: list[sigstore_policy.VerificationPolicy] = [
        sigstore_policy.OIDCIssuer(p.oidc_issuer),
        sigstore_policy.GitHubWorkflowRepository(p.github_repository),
    ]
    if p.workflow_identity_uri:
        predicates.append(sigstore_policy.Identity(identity=p.workflow_identity_uri, issuer=p.oidc_issuer))
    if p.workflow_ref:
        predicates.append(sigstore_policy.GitHubWorkflowRef(p.workflow_ref))
    if p.workflow_sha:
        predicates.append(sigstore_policy.GitHubWorkflowSHA(p.workflow_sha))
    return sigstore_policy.AllOf(predicates)


def _has_rekor_proof(bundle: Bundle) -> bool:
    """True iff the bundle carries a Rekor transparency-log inclusion proof.

    Spec: req-sigstore-core-verify-5 (Rekor-Backed Only).
    """
    try:
        entry = bundle.log_entry
    except Exception:  # noqa: BLE001  # bundle may not expose log_entry at all
        return False
    if entry is None:
        return False
    entries = entry if isinstance(entry, list) else [entry]
    return any(getattr(e, "log_index", None) is not None for e in entries)


def verify_bundle(
    body: bytes,
    bundle_bytes: bytes,
    *,
    policy: VerificationPolicy,
) -> VerificationResult:
    """Verify a Sigstore signature bundle against the given policy.

    Spec: req-sigstore-core-verify (canonical function),
    req-sigstore-core-verify-3 (never raises on verification failure),
    req-sigstore-core-verify-4 (failure code surfaced),
    req-sigstore-core-verify-5 (Rekor-backed only).

    Args:
        body: The artifact bytes being verified (the signed content).
        bundle_bytes: The Sigstore bundle JSON bytes (the .bundle file contents).
        policy: A TAP-side policy descriptor — currently only ``GitHubWorkflowPolicy``.

    Returns:
        A ``VerificationResult``. A parseable-but-failed bundle never raises;
        ``signature_verified`` is set to ``False`` with ``failure_code`` populated.
    """
    verified_at = _utc_now_iso()
    result = VerificationResult(signature_verified=None, verified_at=verified_at)

    # Parse the bundle. Parse failure is a distinct outcome from verification
    # failure: signature_verified stays None.
    try:
        bundle = Bundle.from_json(bundle_bytes)
    except (InvalidBundle, ValueError, KeyError) as exc:
        result.failure_code = "bundle_parse"
        result.failure_detail = str(exc) or type(exc).__name__
        return result

    result.parsed_bundle = bundle
    result.signed_by = _signed_by_from_cert(bundle)
    result.signing_issuer = _signing_issuer_from_cert(bundle)
    log_key_id, log_index, integrated_time, entry_kind = _extract_log_data(bundle)
    result.log_key_id = log_key_id
    result.rekor_log_index = log_index
    result.integrated_time = integrated_time
    result.entry_kind = entry_kind
    # v0 only encounters the public-good Rekor instance; rekor_log_url is the
    # display origin, not part of identity.
    result.rekor_log_url = PUBLIC_GOOD_REKOR_URL

    # Rekor-only fence: bundles without a transparency-log inclusion proof
    # (e.g. RFC3161 timestamp-only) fail v0 verification.
    if not _has_rekor_proof(bundle):
        result.signature_verified = False
        result.failure_code = "no_rekor_proof"
        result.failure_detail = "bundle parsed but contains no Rekor inclusion proof; RFC3161 timestamp-only verification is deferred"
        return result

    try:
        sigstore_pol = _translate_policy(policy)
        _get_verifier().verify_artifact(body, bundle=bundle, policy=sigstore_pol)
    except Exception as exc:  # noqa: BLE001  # see req-sigstore-core-verify-3
        result.signature_verified = False
        result.failure_code = _classify_failure(exc)
        result.failure_detail = str(exc) or type(exc).__name__
        return result

    result.signature_verified = True
    return result


def _classify_failure(exc: BaseException) -> str:
    """Map a sigstore-python verification exception to a v0 failure_code tag.

    The mapping is best-effort: sigstore-python's exception hierarchy is
    not part of TAP's stable surface, so we match by class name strings.
    Unknown exceptions land in ``unexpected``.
    """
    name = type(exc).__name__
    if "Policy" in name or "Identity" in name:
        return "policy_mismatch"
    if "Cert" in name or "Chain" in name:
        return "cert_chain"
    if "Rekor" in name or "Inclusion" in name or "Transparency" in name:
        return "rekor_proof"
    if "Signature" in name:
        return "signature"
    return "unexpected"
