"""Behavior tests for identity_core: the OidcIssuer model + issuer primitives.

Spec: plugins/identity_core/specs/spec-identity-core-v0.md
"""

from __future__ import annotations

from uuid import UUID

import pytest
from tap_plugin.identity_core.issuer import (
    canonical_issuer_url,
    oidc_issuer_id,
    oidc_issuer_node_envelope,
)
from tap_plugin.identity_core.models import OidcIssuer

from tap_grid.caller_context import CallerContext
from tap_grid.models import Entity
from tap_grid.services import WriteOperation, write_batch

_GH_ISSUER = "https://token.actions.githubusercontent.com"
_GH_CANONICAL = "token.actions.githubusercontent.com"


# --- canonical_issuer_url (req-identity-core-canonical-url) ---------------------


class TestCanonicalIssuerUrl:
    def test_strips_scheme(self):
        assert canonical_issuer_url(_GH_ISSUER) == _GH_CANONICAL
        assert canonical_issuer_url("http://example.com") == "example.com"

    def test_scheme_and_schemeless_converge(self):
        """req-identity-core-canonical-url-1: the two forms AWS and github store
        normalize to one key."""
        assert canonical_issuer_url(_GH_ISSUER) == canonical_issuer_url(_GH_CANONICAL)

    def test_lowercases_host(self):
        assert canonical_issuer_url("https://Token.Actions.GitHubUserContent.com") == _GH_CANONICAL

    def test_strips_trailing_slash(self):
        assert canonical_issuer_url(_GH_ISSUER + "/") == _GH_CANONICAL

    def test_preserves_path_case(self):
        """req-identity-core-canonical-url-3: path is preserved (and case-sensitive);
        only the host is lowercased."""
        assert canonical_issuer_url("https://Example.com/Tenant/OIDC") == "example.com/Tenant/OIDC"

    def test_strips_whitespace(self):
        assert canonical_issuer_url("  " + _GH_ISSUER + "  ") == _GH_CANONICAL


# --- oidc_issuer_id (req-identity-core-issuer-id) ------------------------------


class TestOidcIssuerId:
    def test_returns_uuid(self):
        assert isinstance(oidc_issuer_id(_GH_ISSUER), UUID)

    def test_canonical_keyed_convergence(self):
        """req-identity-core-issuer-id-1: scheme'd and scheme-less inputs give one id."""
        assert oidc_issuer_id(_GH_ISSUER) == oidc_issuer_id(_GH_CANONICAL)
        assert oidc_issuer_id(_GH_ISSUER + "/") == oidc_issuer_id(_GH_ISSUER)

    def test_idempotent(self):
        """req-identity-core-issuer-id-3: repeated derivation is stable."""
        assert oidc_issuer_id(_GH_ISSUER) == oidc_issuer_id(_GH_ISSUER)

    def test_distinct_issuers_distinct_ids(self):
        assert oidc_issuer_id(_GH_ISSUER) != oidc_issuer_id("https://accounts.google.com")


# --- oidc_issuer_node_envelope (req-identity-core-envelope) --------------------


class TestNodeEnvelope:
    def test_shape_and_id(self):
        env = oidc_issuer_node_envelope(_GH_ISSUER)
        assert env["entity"]["entity_id"] == str(oidc_issuer_id(_GH_ISSUER))
        assert env["entity"]["entity_type"] == "identity_core__oidc_issuer"
        assert env["entity"]["name"] == _GH_ISSUER
        assert env["entity"]["dimensions"] == {"identity.protocol": "oidc"}

    def test_node_fields(self):
        env = oidc_issuer_node_envelope(_GH_ISSUER)
        assert env["node"]["issuer_url"] == _GH_ISSUER
        assert env["node"]["host"] == _GH_CANONICAL
        assert env["node"]["provider"] == "github-actions"

    def test_provider_blank_for_unknown_issuer(self):
        env = oidc_issuer_node_envelope("https://accounts.google.com")
        assert env["node"]["provider"] == ""

    def test_custom_dimensions(self):
        env = oidc_issuer_node_envelope(_GH_ISSUER, dimensions={"identity.protocol": "oidc", "x": "y"})
        assert env["entity"]["dimensions"]["x"] == "y"

    def test_envelope_and_id_helper_agree(self):
        """The envelope's id is the same one the standalone helper computes — the
        sole-path guarantee (req-identity-core-issuer-id-2) across the two entry points."""
        for raw in (_GH_ISSUER, _GH_CANONICAL, _GH_ISSUER + "/"):
            assert oidc_issuer_node_envelope(raw)["entity"]["entity_id"] == str(oidc_issuer_id(raw))


# --- OidcIssuer model (req-identity-core-model) --------------------------------


@pytest.fixture
def ctx():
    return CallerContext()


def _make_issuer(ctx, issuer_url=_GH_ISSUER, host=_GH_CANONICAL):
    op = WriteOperation(
        verb="create_node",
        type_slug="identity_core__oidc_issuer",
        payload={"issuer_url": issuer_url, "host": host, "provider": "github-actions"},
    )
    result = write_batch([op], caller_context=ctx)
    assert result.results[0].success
    return result.results[0].entity_id


@pytest.mark.django_db
class TestOidcIssuerModel:
    def test_create_via_service_layer(self, ctx):
        iid = _make_issuer(ctx)
        issuer = OidcIssuer.all_objects.get(entity_id=iid)
        assert issuer.issuer_url == _GH_ISSUER
        assert issuer.host == _GH_CANONICAL
        assert issuer.provider == "github-actions"

    def test_issuer_url_required(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="identity_core__oidc_issuer",
            payload={"host": _GH_CANONICAL},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_default_dimensions_applied(self, ctx):
        iid = _make_issuer(ctx)
        entity = Entity.objects.get(pk=iid)
        assert entity.dimensions.get("identity.protocol") == "oidc"

    def test_entity_name_is_issuer_url(self, ctx):
        """req-identity-core-model: get_name() is the issuer_url — no well-known
        catalog. Entity.name projects from it (req-grid-node-display)."""
        iid = _make_issuer(ctx)
        entity = Entity.objects.get(pk=iid)
        assert entity.name == _GH_ISSUER
