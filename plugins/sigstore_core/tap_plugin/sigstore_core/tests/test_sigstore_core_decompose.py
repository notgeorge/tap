"""Hermetic tests for ``tap_plugin.sigstore_core.decompose``.

The decompose helper draws all its data from ``VerificationResult`` and the
caller-supplied policy/dimensions/identity. The parsed_bundle attribute on
``VerificationResult`` is required to be non-``None`` (per
req-sigstore-core-decompose-3) but is otherwise opaque to the helper, so
these tests use a sentinel object in its place. No real Sigstore bundle is
needed; no network call is made; no other plugin's artifacts are touched.
"""

from __future__ import annotations

import pytest
from tap_plugin.sigstore_core.decompose import GriftFragment, bundle_to_grift_fragment
from tap_plugin.sigstore_core.verify import (
    PUBLIC_GOOD_FULCIO_URL,
    PUBLIC_GOOD_REKOR_URL,
    GitHubWorkflowPolicy,
    VerificationResult,
)


def _good_result(*, signature_verified: bool = True) -> VerificationResult:
    """Build a synthesized VerificationResult that's shaped like a verified bundle.

    `parsed_bundle` is a sentinel — the helper checks `is None` but never
    introspects it, so any non-None object satisfies the contract.
    """
    return VerificationResult(
        signature_verified=signature_verified,
        signed_by="https://github.com/example/repo/.github/workflows/publish.yml@refs/heads/main",
        signing_issuer="https://token.actions.githubusercontent.com",
        log_key_id="abcdef0123456789",
        rekor_log_url=PUBLIC_GOOD_REKOR_URL,
        rekor_log_index="42",
        integrated_time="2026-05-27T12:00:00Z",
        entry_kind="hashedrekord",
        verified_at="2026-05-27T12:00:05Z",
        failure_code="" if signature_verified else "policy_mismatch",
        failure_detail="" if signature_verified else "wrong repo",
        parsed_bundle=object(),  # opaque non-None sentinel
    )


def _policy() -> GitHubWorkflowPolicy:
    return GitHubWorkflowPolicy(
        oidc_issuer="https://token.actions.githubusercontent.com",
        github_repository="example/repo",
    )


class TestUnparseableRefused:
    """Spec: req-sigstore-core-decompose-3."""

    def test_none_parsed_bundle_raises(self) -> None:
        result = _good_result()
        result.parsed_bundle = None
        with pytest.raises(ValueError, match="parsed_bundle"):
            bundle_to_grift_fragment(
                result,
                anchor_entity_id="anchor-1",
                policy=_policy(),
                dimensions={},
            )


class TestFourPieceFragment:
    """Spec: req-sigstore-core-decompose-1, req-sigstore-core-decompose-2."""

    def test_returns_grift_fragment(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        assert isinstance(fragment, GriftFragment)

    def test_four_pieces_without_identity(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        # 2 entities (sigstore_ca + rekor_log_entry), 2 edges (CERT_ISSUED_BY + ATTESTED_BY)
        assert len(fragment.entities) == 2
        assert len(fragment.edges) == 2

    def test_entities_are_ca_and_log_entry(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        types = {e["entity_type"] for e in fragment.entities}
        assert types == {"sigstore_core__sigstore_ca", "sigstore_core__rekor_log_entry"}

    def test_edges_are_cert_issued_by_and_attested_by(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        types = {e["edge_type"] for e in fragment.edges}
        assert types == {"CERT_ISSUED_BY__sigstore_core", "ATTESTED_BY__sigstore_core"}


class TestFivePieceFragmentWithIdentity:
    """Spec: req-sigstore-core-edges-5 (caller-supplied identity),
    req-sigstore-core-decompose-2 (shape).

    A resolved signing identity emits two edges (same precondition): the
    verifier-walk ``SIGNED_BY_IDENTITY`` (Rekor entry -> identity) and the
    action edge ``REQUESTS_SIGSTORE_SIGNATURE`` (identity -> Fulcio CA), per the
    edge catalog in spec-sigstore-core-v0.md."""

    def test_identity_supplied_emits_identity_edges(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
            signing_identity_entity_id="github-workflow-42",
        )
        assert len(fragment.edges) == 4
        types = {e["edge_type"] for e in fragment.edges}
        assert types == {
            "CERT_ISSUED_BY__sigstore_core",
            "ATTESTED_BY__sigstore_core",
            "SIGNED_BY_IDENTITY__sigstore_core",
            "REQUESTS_SIGSTORE_SIGNATURE__sigstore_core",
        }

    def test_requests_signature_edge_runs_identity_to_ca(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
            signing_identity_entity_id="github-workflow-42",
        )
        requests = next(e for e in fragment.edges if e["edge_type"] == "REQUESTS_SIGSTORE_SIGNATURE__sigstore_core")
        # Source is the signing identity; target is the issuing Fulcio CA node.
        assert requests["source_entity_id"] == "github-workflow-42"
        ca = next(e for e in fragment.entities if e["entity_type"] == "sigstore_core__sigstore_ca")
        assert requests["target_entity_id"] == ca["entity_id"]

    def test_signed_by_identity_edge_targets_the_supplied_entity(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
            signing_identity_entity_id="github-workflow-42",
        )
        signed = next(e for e in fragment.edges if e["edge_type"] == "SIGNED_BY_IDENTITY__sigstore_core")
        assert signed["target_entity_id"] == "github-workflow-42"
        # Source is the Rekor entry — same id as the log_entry node's entity_id.
        entry = next(e for e in fragment.entities if e["entity_type"] == "sigstore_core__rekor_log_entry")
        assert signed["source_entity_id"] == entry["entity_id"]


class TestFailedVerdictEmitted:
    """Spec: req-sigstore-core-decompose-5 (failed verdicts emitted, not silently dropped)."""

    def test_failed_verdict_still_emits_full_fragment(self) -> None:
        result = _good_result(signature_verified=False)
        fragment = bundle_to_grift_fragment(
            result,
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        assert len(fragment.entities) == 2
        assert len(fragment.edges) == 2

    def test_failed_verdict_attrs_on_attested_by(self) -> None:
        result = _good_result(signature_verified=False)
        fragment = bundle_to_grift_fragment(
            result,
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        attested = next(e for e in fragment.edges if e["edge_type"] == "ATTESTED_BY__sigstore_core")
        assert attested["properties"]["signature_verified"] is False
        assert attested["properties"]["verification_failure_code"] == "policy_mismatch"
        assert attested["properties"]["verification_failure_detail"] == "wrong repo"


class TestAttestedByPolicyAttributes:
    """Spec: req-sigstore-core-edges-4 (verdict on edge),
    req-sigstore-core-policy-3 (applied predicates recorded)."""

    def test_policy_kind_is_github_workflow(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        attested = next(e for e in fragment.edges if e["edge_type"] == "ATTESTED_BY__sigstore_core")
        assert attested["properties"]["policy_kind"] == "github_core__github_workflow"
        assert attested["properties"]["policy_oidc_issuer"] == "https://token.actions.githubusercontent.com"
        assert attested["properties"]["policy_github_repository"] == "example/repo"

    def test_optional_policy_predicates_recorded(self) -> None:
        policy = GitHubWorkflowPolicy(
            oidc_issuer="https://token.actions.githubusercontent.com",
            github_repository="example/repo",
            workflow_identity_uri="https://github.com/example/repo/.github/workflows/publish.yml@refs/heads/main",
            workflow_ref="refs/heads/main",
            workflow_sha="0123456789abcdef0123456789abcdef01234567",
        )
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=policy,
            dimensions={},
        )
        attested = next(e for e in fragment.edges if e["edge_type"] == "ATTESTED_BY__sigstore_core")
        assert attested["properties"]["policy_workflow_identity_uri"].endswith("@refs/heads/main")
        assert attested["properties"]["policy_workflow_ref"] == "refs/heads/main"
        assert attested["properties"]["policy_workflow_sha"].startswith("0123456789")

    def test_optional_predicates_absent_when_not_supplied(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),  # only required fields
            dimensions={},
        )
        attested = next(e for e in fragment.edges if e["edge_type"] == "ATTESTED_BY__sigstore_core")
        for absent_key in ("policy_workflow_identity_uri", "policy_workflow_ref", "policy_workflow_sha"):
            assert absent_key not in attested["properties"]


class TestSigstoreCaUpsert:
    def test_public_good_fulcio_defaults(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        ca = next(e for e in fragment.entities if e["entity_type"] == "sigstore_core__sigstore_ca")
        assert ca["fields"]["ca_url"] == PUBLIC_GOOD_FULCIO_URL
        assert ca["fields"]["ca_kind"] == "fulcio"
        assert ca["fields"]["trust_root_source"] == "tuf-public-good"


class TestRekorLogEntryFields:
    def test_immutable_facts_only(self) -> None:
        """req-sigstore-core-models-3: rekor_log_entry carries only immutable facts.

        Verdict, policy attrs, and failure code/detail must NOT appear as fields
        on the node — they live on ATTESTED_BY.
        """
        fragment = bundle_to_grift_fragment(
            _good_result(signature_verified=False),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        entry = next(e for e in fragment.entities if e["entity_type"] == "sigstore_core__rekor_log_entry")
        verdict_leakage = {
            "signature_verified",
            "verified_at",
            "verification_failure_code",
            "verification_failure_detail",
            "policy_kind",
            "policy_oidc_issuer",
            "policy_github_repository",
        }
        assert set(entry["fields"]).isdisjoint(verdict_leakage)

    def test_documented_fields_populated(self) -> None:
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        entry = next(e for e in fragment.entities if e["entity_type"] == "sigstore_core__rekor_log_entry")
        f = entry["fields"]
        assert f["log_key_id"] == "abcdef0123456789"
        assert f["log_index"] == 42
        assert f["rekor_log_url"] == PUBLIC_GOOD_REKOR_URL
        assert f["integrated_time"] == "2026-05-27T12:00:00Z"
        assert f["entry_kind"] == "hashedrekord"
        assert f["signing_identity_uri"].endswith("@refs/heads/main")
        assert f["signing_identity_issuer"] == "https://token.actions.githubusercontent.com"


class TestDeterministicEntityIds:
    """Same input → same UUIDs across calls (UUIDv5 under the sigstore_core namespace)."""

    def test_repeated_calls_yield_same_ids(self) -> None:
        f1 = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        f2 = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions={},
        )
        e1_ids = {e["entity_type"]: e["entity_id"] for e in f1.entities}
        e2_ids = {e["entity_type"]: e["entity_id"] for e in f2.entities}
        assert e1_ids == e2_ids

    def test_different_log_index_yields_different_entry_id(self) -> None:
        r1 = _good_result()
        r2 = _good_result()
        r2.rekor_log_index = "99"
        f1 = bundle_to_grift_fragment(r1, anchor_entity_id="anchor-1", policy=_policy(), dimensions={})
        f2 = bundle_to_grift_fragment(r2, anchor_entity_id="anchor-1", policy=_policy(), dimensions={})
        e1 = next(e for e in f1.entities if e["entity_type"] == "sigstore_core__rekor_log_entry")
        e2 = next(e for e in f2.entities if e["entity_type"] == "sigstore_core__rekor_log_entry")
        assert e1["entity_id"] != e2["entity_id"]


class TestDimensionPropagation:
    def test_caller_dimensions_applied_to_all_pieces(self) -> None:
        dims = {"sigstore.platform": "public-good", "example.scope": "compliance"}
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions=dims,
        )
        for entity in fragment.entities:
            assert entity["dimensions"] == dims
        for edge in fragment.edges:
            assert edge["dimensions"] == dims

    def test_dimensions_copied_not_shared(self) -> None:
        """Mutating the caller's dimensions dict after the call must not mutate the fragment."""
        dims = {"sigstore.platform": "public-good"}
        fragment = bundle_to_grift_fragment(
            _good_result(),
            anchor_entity_id="anchor-1",
            policy=_policy(),
            dimensions=dims,
        )
        dims["sigstore.platform"] = "MUTATED"
        for entity in fragment.entities:
            assert entity["dimensions"]["sigstore.platform"] == "public-good"
