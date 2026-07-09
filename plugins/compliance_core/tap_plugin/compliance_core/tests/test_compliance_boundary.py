"""Behavior tests for the ComplianceBoundary model and SCOPED_TO_COMPLIANCE_BOUNDARY edge.

Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-boundary.md
"""

from __future__ import annotations

import pytest
from tap_plugin.compliance_core.models import ComplianceBoundary

from tap_grid.caller_context import CallerContext
from tap_grid.models import Edge, Entity
from tap_grid.services import WriteOperation, write_batch


@pytest.fixture
def ctx():
    return CallerContext()


def _make_boundary(ctx, name="Test ComplianceBoundary"):
    op = WriteOperation(
        verb="create_node",
        type_slug="compliance_core__compliance_boundary",
        payload={"name": name, "description": "fixture boundary"},
    )
    result = write_batch([op], caller_context=ctx)
    assert result.results[0].success
    return result.results[0].entity_id


def _make_finding(ctx, name="Test ComplianceFinding"):
    op = WriteOperation(
        verb="create_node",
        type_slug="compliance_core__compliance_finding",
        payload={"name": name},
    )
    result = write_batch([op], caller_context=ctx)
    assert result.results[0].success
    return result.results[0].entity_id


@pytest.mark.django_db
class TestBoundaryModel:
    def test_create_via_service_layer(self, ctx):
        bid = _make_boundary(ctx, "Samsite Authorization ComplianceBoundary")
        b = ComplianceBoundary.all_objects.get(entity_id=bid)
        assert b.name == "Samsite Authorization ComplianceBoundary"
        assert b.description == "fixture boundary"

    def test_name_required(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="compliance_core__compliance_boundary",
            payload={"description": "no name"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_default_dimensions_applied(self, ctx):
        bid = _make_boundary(ctx)
        entity = Entity.objects.get(pk=bid)
        assert entity.dimensions.get("compliance") == "boundary"

    def test_entity_name_synced_from_get_name(self, ctx):
        """req-grid-node-display: Entity.name is projected from get_name()."""
        bid = _make_boundary(ctx, "Perimeter Alpha")
        entity = Entity.objects.get(pk=bid)
        assert entity.name == "Perimeter Alpha"


@pytest.mark.django_db
class TestScopedToBoundaryEdge:
    def test_component_scoped_to_boundary(self, ctx):
        """A component (wildcard source) links to a boundary target."""
        bid = _make_boundary(ctx)
        fid = _make_finding(ctx)
        op = WriteOperation(
            verb="create_edge",
            from_target=fid,
            to_target=bid,
            edge_type="SCOPED_TO_COMPLIANCE_BOUNDARY__compliance_core",
            payload={},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        edge = Edge.objects.get(entity_id=result.results[0].entity_id)
        assert edge.edge_type == "SCOPED_TO_COMPLIANCE_BOUNDARY__compliance_core"

    def test_edge_targets_constraint_is_boundary_only(self):
        """The edge declares `targets = ["boundary"]`.

        Asserts the registered constraint directly. (Hard rejection of a
        non-boundary target additionally depends on the receiving node's
        inbound constraints — the constraint system uses Permission Union,
        where an unconstrained node permits any inbound edge. The edge-side
        `targets` declaration is the contract this test pins.)
        """
        from tap_grid.constraints import _edge_allows_target

        assert _edge_allows_target("compliance_core__compliance_boundary", "SCOPED_TO_COMPLIANCE_BOUNDARY__compliance_core") is True
        assert _edge_allows_target("compliance_core__compliance_finding", "SCOPED_TO_COMPLIANCE_BOUNDARY__compliance_core") is False

    def test_default_dimensions_applied(self, ctx):
        bid = _make_boundary(ctx)
        fid = _make_finding(ctx)
        op = WriteOperation(
            verb="create_edge",
            from_target=fid,
            to_target=bid,
            edge_type="SCOPED_TO_COMPLIANCE_BOUNDARY__compliance_core",
            payload={},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        edge = Edge.objects.get(entity_id=result.results[0].entity_id)
        assert edge.entity.dimensions.get("compliance") == "boundary"
