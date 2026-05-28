"""Hermetic tests for ``plugins.sigstore_core.verify``.

Scope: behavior that can be exercised without a real Sigstore bundle and
without touching the network or any other plugin's artifacts. The
happy-path verification, policy-mismatch verification, and
``no_rekor_proof`` enforcement paths require a real Rekor-backed bundle
and are deferred to the platform live-integration test harness
(``req-tap-test-live-integration-backlog`` in ``specs/spec-tap-testing.md``
and ``req-sigstore-core-testing-backlog`` in this plugin's spec).
"""

from __future__ import annotations

import dataclasses

import pytest

from plugins.sigstore_core.verify import (
    GitHubWorkflowPolicy,
    VerificationResult,
    _classify_failure,
    verify_bundle,
)


class TestGitHubWorkflowPolicy:
    """Spec: req-sigstore-core-policy-2 (GitHubWorkflowPolicy shipped)."""

    def test_required_fields_only(self) -> None:
        p = GitHubWorkflowPolicy(
            oidc_issuer="https://token.actions.githubusercontent.com",
            github_repository="example/repo",
        )
        assert p.workflow_identity_uri is None
        assert p.workflow_ref is None
        assert p.workflow_sha is None

    def test_all_optional_predicates(self) -> None:
        p = GitHubWorkflowPolicy(
            oidc_issuer="https://token.actions.githubusercontent.com",
            github_repository="example/repo",
            workflow_identity_uri="https://github.com/example/repo/.github/workflows/publish.yml@refs/heads/main",
            workflow_ref="refs/heads/main",
            workflow_sha="0123456789abcdef0123456789abcdef01234567",
        )
        assert p.workflow_identity_uri.endswith("@refs/heads/main")
        assert p.workflow_ref == "refs/heads/main"
        assert p.workflow_sha == "0123456789abcdef0123456789abcdef01234567"

    def test_frozen(self) -> None:
        p = GitHubWorkflowPolicy(oidc_issuer="x", github_repository="y")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.oidc_issuer = "z"  # type: ignore[misc]


class TestVerifyBundleParseFailure:
    """Spec: req-sigstore-core-verify-2 (three-state result),
    req-sigstore-core-verify-4 (failure code surfaced)."""

    def _policy(self) -> GitHubWorkflowPolicy:
        return GitHubWorkflowPolicy(
            oidc_issuer="https://token.actions.githubusercontent.com",
            github_repository="example/repo",
        )

    def test_garbage_bytes_yield_bundle_parse_failure(self) -> None:
        result = verify_bundle(b"hello world", b"not a bundle", policy=self._policy())
        assert result.signature_verified is None
        assert result.failure_code == "bundle_parse"
        assert result.failure_detail != ""
        # Identity / log fields are empty on parse failure.
        assert result.signed_by == ""
        assert result.signing_issuer == ""
        assert result.log_key_id == ""
        assert result.rekor_log_index == ""
        assert result.parsed_bundle is None

    def test_empty_bundle_yields_bundle_parse_failure(self) -> None:
        result = verify_bundle(b"", b"", policy=self._policy())
        assert result.signature_verified is None
        assert result.failure_code == "bundle_parse"
        assert result.parsed_bundle is None

    def test_invalid_json_yields_bundle_parse_failure(self) -> None:
        result = verify_bundle(b"x", b'{"not": "a sigstore bundle"}', policy=self._policy())
        assert result.signature_verified is None
        assert result.failure_code == "bundle_parse"

    def test_verified_at_always_populated(self) -> None:
        """verified_at is populated even on parse failure (it's when *we* tried)."""
        result = verify_bundle(b"x", b"garbage", policy=self._policy())
        assert result.verified_at != ""
        # ISO 8601 UTC, ends with Z.
        assert result.verified_at.endswith("Z")


class TestVerificationResultShape:
    """The dataclass exists with the documented fields and three-state ``signature_verified``."""

    def test_default_construction(self) -> None:
        r = VerificationResult(signature_verified=None)
        assert r.signature_verified is None
        assert r.signed_by == ""
        assert r.failure_code == ""
        assert r.parsed_bundle is None

    def test_three_state_signature_verified(self) -> None:
        for value in (True, False, None):
            r = VerificationResult(signature_verified=value)
            assert r.signature_verified is value


class TestClassifyFailure:
    """Spec: ``_classify_failure`` maps representative sigstore-python exception
    class names to the v0 failure_code vocabulary documented in
    req-sigstore-core-verify."""

    def test_policy_class_names_map_to_policy_mismatch(self) -> None:
        class PolicyError(Exception):
            pass

        class IdentityError(Exception):
            pass

        assert _classify_failure(PolicyError()) == "policy_mismatch"
        assert _classify_failure(IdentityError()) == "policy_mismatch"

    def test_cert_class_names_map_to_cert_chain(self) -> None:
        class CertError(Exception):
            pass

        class ChainError(Exception):
            pass

        assert _classify_failure(CertError()) == "cert_chain"
        assert _classify_failure(ChainError()) == "cert_chain"

    def test_rekor_class_names_map_to_rekor_proof(self) -> None:
        class RekorError(Exception):
            pass

        class InclusionError(Exception):
            pass

        class TransparencyError(Exception):
            pass

        assert _classify_failure(RekorError()) == "rekor_proof"
        assert _classify_failure(InclusionError()) == "rekor_proof"
        assert _classify_failure(TransparencyError()) == "rekor_proof"

    def test_signature_class_names_map_to_signature(self) -> None:
        class SignatureError(Exception):
            pass

        assert _classify_failure(SignatureError()) == "signature"

    def test_unknown_class_name_maps_to_unexpected(self) -> None:
        class WeirdThing(Exception):
            pass

        assert _classify_failure(WeirdThing()) == "unexpected"
        assert _classify_failure(RuntimeError("anything")) == "unexpected"
