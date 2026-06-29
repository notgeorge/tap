"""Behavior tests for the Evidence model and HAS_EVIDENCE edge."""

from __future__ import annotations

import pytest
from django.utils import timezone

from plugins.fedramp_20x_ksi.models import Evidence, Finding
from tap_grid.caller_context import CallerContext
from tap_grid.models import Edge, Entity
from tap_grid.services import WriteOperation, write_batch


@pytest.fixture
def ctx():
    return CallerContext()


@pytest.fixture
def finding(ctx):
    op = WriteOperation(
        verb="create_node",
        type_slug="finding",
        payload={"name": "Test finding", "description": "fixture", "status": "open"},
    )
    result = write_batch([op], caller_context=ctx)
    assert result.results[0].success
    finding_id = result.results[0].entity_id
    yield Finding.all_objects.get(entity_id=finding_id)
    Entity.objects.filter(pk=finding_id).update(deleted_at=timezone.now())


@pytest.mark.django_db
class TestEvidenceModel:
    def test_create_via_service_layer(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={
                "name": "AWS Config screenshot",
                "description": "Shows MFA is enabled.",
                "kind": "screenshot",
            },
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        ev = Evidence.all_objects.get(entity_id=result.results[0].entity_id)
        assert ev.name == "AWS Config screenshot"
        assert ev.kind == "screenshot"

    def test_required_fields_enforced(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={"description": "no name, no kind"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_kind_enum_enforced(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={"name": "bad kind", "kind": "bogus_kind"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_default_dimensions_applied(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={"name": "dim test", "kind": "other"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        entity = Entity.objects.get(pk=result.results[0].entity_id)
        assert entity.dimensions.get("compliance") == "fedramp-20x"

    def test_display_name_synced_to_spine(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={"name": "Spine sync test", "kind": "attestation"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        ev = Evidence.all_objects.get(entity_id=result.results[0].entity_id)
        assert ev.entity.name == "Spine sync test"


@pytest.mark.django_db
class TestHasEvidenceEdge:
    def _make_evidence(self, ctx, name: str = "ev") -> str:
        op = WriteOperation(
            verb="create_node",
            type_slug="evidence",
            payload={"name": name, "kind": "scanner_output"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        return result.results[0].entity_id

    def test_create_passing_edge(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "passing-ev")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "passing"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        edge = Edge.objects.get(entity_id=result.results[0].entity_id)
        assert edge.edge_type == "HAS_EVIDENCE"
        assert edge.properties["support_kind"] == "passing"

    def test_create_violation_edge(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "violation-ev")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "violation"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success

    def test_create_informational_edge(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "info-ev")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "informational"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success

    def test_invalid_support_kind_rejected(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "bad-ev")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "bogus"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_missing_support_kind_rejected(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "no-kind")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {}},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_unknown_property_rejected(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "extra-prop")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "passing", "rogue": "field"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_default_dimensions_applied_to_edge(self, ctx, finding):
        ev_id = self._make_evidence(ctx, "dim-edge")
        op = WriteOperation(
            verb="create_edge",
            from_target=str(finding.entity_id),
            to_target=ev_id,
            edge_type="HAS_EVIDENCE",
            payload={"properties": {"support_kind": "passing"}},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        edge_entity = Entity.objects.get(pk=result.results[0].entity_id)
        assert edge_entity.dimensions.get("compliance") == "fedramp-20x"
