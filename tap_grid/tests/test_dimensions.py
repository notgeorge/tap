"""Tests for tap_grid dimension requirements.

Covers:
  req-grid-dimension-em  — dimensions field on Entity
  req-grid-dimension-dc  — DEFAULT_DIMENSIONS applied at creation; Edge inherits source
  req-grid-dimension-dn  — Dimension node model
"""

import pytest

from tap_grid.models import Dimension, Edge, Entity
from tap_grid.services import create_entity
from tap_plugins.core_examples.models import Concept, Precept


# ---------------------------------------------------------------------------
# req-grid-dimension-em: Dimensions on Entity Model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEntityDimensionsField:
    """req-grid-dimension-em: dimensions JSONField exists, non-nullable, default {}."""

    def test_dimensions_defaults_to_empty_dict(self):
        """New Entity gets dimensions={} by default (em-1, em-2)."""
        entity = create_entity("concept")
        assert entity.dimensions == {}

    def test_dimensions_can_be_set_on_create(self):
        """Entity.objects.create() accepts explicit dimensions (em-1)."""
        entity = create_entity("concept", dimensions={"env": "staging"})
        assert entity.dimensions == {"env": "staging"}

    def test_dimensions_persists_after_save(self):
        """Dimensions round-trip correctly through the DB (em-1)."""
        entity = create_entity("concept", dimensions={"tap.graph": "web", "env": "prod"})
        entity.refresh_from_db()
        assert entity.dimensions == {"tap.graph": "web", "env": "prod"}

    def test_dimensions_field_is_non_nullable(self):
        """The dimensions field is non-nullable; the DB stores a dict (em-2)."""
        entity = create_entity("concept")
        entity.refresh_from_db()
        assert entity.dimensions is not None
        assert isinstance(entity.dimensions, dict)


# ---------------------------------------------------------------------------
# req-grid-dimension-dc: Default Dimension Application
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDefaultDimensions:
    """req-grid-dimension-dc: DEFAULT_DIMENSIONS applied to backing Entity on create.

    Dimension nodes (DEFAULT_DIMENSIONS = {"tap.meta": "dimension"}) serve as the
    concrete driver for these tests — no need for a separate test model.
    """

    def test_default_dimensions_applied(self):
        """Creating a model with DEFAULT_DIMENSIONS populates the backing Entity (dc-1)."""
        dim = Dimension.objects.create(name="web")
        assert dim.entity.dimensions == {"tap.meta": "dimension"}

    def test_explicit_wins_over_default(self):
        """Caller-supplied _initial_dimensions overrides overlapping defaults (dc-3)."""
        dim = Dimension(name="custom")
        dim._initial_dimensions = {"tap.meta": "custom-override"}
        dim.save()
        assert dim.entity.dimensions == {"tap.meta": "custom-override"}

    def test_non_overlapping_keys_merged(self):
        """Non-overlapping keys from defaults and caller are both present (dc-3)."""
        dim = Dimension(name="merged")
        dim._initial_dimensions = {"env": "staging"}
        dim.save()
        assert dim.entity.dimensions == {"tap.meta": "dimension", "env": "staging"}

    def test_defaults_not_enforced_after_creation(self):
        """Changing dimensions after creation causes no validation error (dc-2)."""
        dim = Dimension.objects.create(name="mutable")
        dim.entity.dimensions = {}
        dim.entity.save(update_fields=["dimensions", "updated_at"])
        dim.entity.refresh_from_db()
        assert dim.entity.dimensions == {}

    def test_model_without_defaults_gets_empty_dims(self):
        """Model without DEFAULT_DIMENSIONS gets dimensions={} on the Entity (dc-1)."""
        concept = Concept.objects.create(summary="no defaults")
        assert concept.entity.dimensions == {}


@pytest.mark.django_db
class TestEdgeDimensionInheritance:
    """req-grid-dimension-dc-4: Edge inherits DEFAULT_DIMENSIONS from its source node."""

    def test_edge_inherits_source_dimensions(self):
        """Edge backing Entity gets source node's DEFAULT_DIMENSIONS (dc-4)."""
        # Dimension node has DEFAULT_DIMENSIONS = {"tap.meta": "dimension"}
        source_dim = Dimension.objects.create(name="source-dim")
        target = Concept.objects.create(summary="target")

        edge = Edge.objects.create(
            from_entity=source_dim.entity,
            to_entity=target.entity,
            edge_type="TEST",
        )
        assert edge.entity.dimensions == {"tap.meta": "dimension"}

    def test_edge_caller_dims_override_source(self):
        """Caller-supplied _initial_dimensions on Edge override source defaults (dc-4)."""
        source_dim = Dimension.objects.create(name="source-dim2")
        target = Concept.objects.create(summary="target2")

        edge = Edge(from_entity=source_dim.entity, to_entity=target.entity, edge_type="TEST")
        edge._initial_dimensions = {"tap.meta": "override"}
        edge.save()
        assert edge.entity.dimensions == {"tap.meta": "override"}

    def test_edge_caller_adds_non_overlapping_key(self):
        """Caller key that doesn't overlap with source defaults is also present (dc-4)."""
        source_dim = Dimension.objects.create(name="source-dim3")
        target = Concept.objects.create(summary="target3")

        edge = Edge(from_entity=source_dim.entity, to_entity=target.entity, edge_type="TEST")
        edge._initial_dimensions = {"env": "staging"}
        edge.save()
        assert edge.entity.dimensions == {"tap.meta": "dimension", "env": "staging"}

    def test_edge_from_undimensioned_source_gets_empty(self):
        """Edge from a source with no DEFAULT_DIMENSIONS gets dimensions={} (dc-4)."""
        source = Concept.objects.create(summary="no dims source")
        target = Precept.objects.create(statement="target")
        edge = Edge.objects.create(
            from_entity=source.entity,
            to_entity=target.entity,
            edge_type="APPLIES_TO",
        )
        assert edge.entity.dimensions == {}


# ---------------------------------------------------------------------------
# req-grid-dimension-dn: Dimension Node
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDimensionNode:
    """req-grid-dimension-dn: Dimension model declaration and self-tagging."""

    def test_dimension_entity_type(self):
        """Dimension is a concrete BaseModel subclass with ENTITY_TYPE='dimension' (dn-1)."""
        dim = Dimension.objects.create(name="web", description="Web UI entities")
        assert dim.entity.entity_type == "dimension"

    def test_dimension_nodes_self_tagged(self):
        """Dimension nodes get tap.meta=dimension on their backing Entity (dn-2)."""
        dim = Dimension.objects.create(name="data", description="Core data dimension")
        assert dim.entity.dimensions == {"tap.meta": "dimension"}

    def test_dimension_carries_name_and_description(self):
        """Dimension model has name and description fields (dn-3)."""
        dim = Dimension.objects.create(name="ops", description="Operational dimension")
        dim.refresh_from_db()
        assert dim.name == "ops"
        assert dim.description == "Operational dimension"

    def test_dimension_str(self):
        """__str__ returns the name."""
        dim = Dimension(name="human")
        assert str(dim) == "human"

    def test_dimension_registered_in_model_registry(self):
        """Dimension is accessible via the model registry (dn-1)."""
        from tap_grid.registry import get_model_class

        assert get_model_class("dimension") is Dimension

    def test_dimension_on_spine(self):
        """Every Dimension has a backing Entity row (dn-1)."""
        dim = Dimension.objects.create(name="spine-check")
        assert Entity.objects.filter(pk=dim.entity_id).exists()
