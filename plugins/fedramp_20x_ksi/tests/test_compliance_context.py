"""Behavior tests for the ComplianceContext model."""

from __future__ import annotations

import pytest

from tap_plugin.fedramp_20x_ksi.models import ComplianceContext
from tap_grid.caller_context import CallerContext
from tap_grid.models import Entity
from tap_grid.services import WriteOperation, write_batch


@pytest.fixture
def ctx():
    return CallerContext()


@pytest.mark.django_db
class TestComplianceContextModel:
    def test_create_via_service_layer(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={
                "name": "Test Compliance Context",
                "description": "fixture",
                "regime": "fedramp_20x",
                "fedramp_class": "c",
            },
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        cc = ComplianceContext.all_objects.get(
            entity_id=result.results[0].entity_id
        )
        assert cc.name == "Test Compliance Context"
        assert cc.regime == "fedramp_20x"
        assert cc.fedramp_class == "c"

    def test_default_fedramp_class_is_b(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "Default Class Test", "regime": "fedramp_20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        cc = ComplianceContext.all_objects.get(
            entity_id=result.results[0].entity_id
        )
        assert cc.fedramp_class == "b"

    def test_name_required(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"description": "no name", "regime": "fedramp_20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_regime_required(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "no regime"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_regime_pattern_enforced(self, ctx):
        """Regime slugs must be lowercase snake_case-friendly identifiers."""
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "bad regime", "regime": "FedRAMP 20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_fedramp_class_enum_enforced(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={
                "name": "bogus class",
                "regime": "fedramp_20x",
                "fedramp_class": "z",
            },
        )
        result = write_batch([op], caller_context=ctx)
        assert not result.results[0].success

    def test_empty_fedramp_class_allowed(self, ctx):
        """Empty string explicitly means 'FedRAMP not in scope for this context'."""
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={
                "name": "SOC2 Context",
                "regime": "soc2",
                "fedramp_class": "",
            },
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        cc = ComplianceContext.all_objects.get(
            entity_id=result.results[0].entity_id
        )
        assert cc.fedramp_class == ""
        assert cc.regime == "soc2"

    def test_default_dimensions_applied(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "dim test", "regime": "fedramp_20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        entity = Entity.objects.get(pk=result.results[0].entity_id)
        assert entity.dimensions.get("compliance") == "context"

    def test_per_regime_dimension_override(self, ctx):
        """Callers may override DEFAULT_DIMENSIONS to carry the regime's dimension."""
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={
                "name": "FedRAMP-dimensioned context",
                "regime": "fedramp_20x",
            },
            dimensions={"compliance": "fedramp-20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        entity = Entity.objects.get(pk=result.results[0].entity_id)
        assert entity.dimensions.get("compliance") == "fedramp-20x"

    def test_multiple_contexts_coexist_per_regime(self, ctx):
        """One ComplianceContext per regime — multiple regimes coexist on a Grid."""
        ops = [
            WriteOperation(
                verb="create_node",
                type_slug="fedramp_20x_ksi__compliance_context",
                payload={
                    "name": "FedRAMP Context",
                    "regime": "fedramp_20x",
                    "fedramp_class": "b",
                },
            ),
            WriteOperation(
                verb="create_node",
                type_slug="fedramp_20x_ksi__compliance_context",
                payload={
                    "name": "SOC2 Context",
                    "regime": "soc2",
                    "fedramp_class": "",
                },
            ),
        ]
        result = write_batch(ops, caller_context=ctx)
        assert all(r.success for r in result.results)
        regimes = set(
            ComplianceContext.all_objects.values_list("regime", flat=True)
        )
        assert {"fedramp_20x", "soc2"}.issubset(regimes)

    def test_display_name_synced_to_spine(self, ctx):
        op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "Spine Sync Test", "regime": "fedramp_20x"},
        )
        result = write_batch([op], caller_context=ctx)
        assert result.results[0].success
        cc = ComplianceContext.all_objects.get(
            entity_id=result.results[0].entity_id
        )
        assert cc.entity.name == "Spine Sync Test"

    def test_update_propagates_to_spine(self, ctx):
        create_op = WriteOperation(
            verb="create_node",
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "Initial Name", "regime": "fedramp_20x"},
        )
        result = write_batch([create_op], caller_context=ctx)
        assert result.results[0].success
        eid = result.results[0].entity_id

        update_op = WriteOperation(
            verb="patch_node",
            target=eid,
            type_slug="fedramp_20x_ksi__compliance_context",
            payload={"name": "Updated Name", "fedramp_class": "d"},
        )
        result = write_batch([update_op], caller_context=ctx)
        assert result.results[0].success

        cc = ComplianceContext.all_objects.get(entity_id=eid)
        assert cc.name == "Updated Name"
        assert cc.fedramp_class == "d"
        assert cc.entity.name == "Updated Name"
