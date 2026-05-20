"""Drift guard for the canonical Entity spine field list.

req-grid-entity-spine-surface declares `Entity.SPINE_FIELD_NAMES` as
the single source of truth for what lives on the Entity row, used by
both the envelope serializer (`tap_grid.grift.subgraph.build_spine_surface`)
and the Gryphon path compiler (envelope-aware paths,
req-grid-traversal-lang-envelope-paths).

These tests ensure the canonical tuple does not drift from the actual
Entity model. Adding a field to Entity without updating
SPINE_FIELD_NAMES reds this test.
"""

from __future__ import annotations

import pytest

from tap_grid.models import Entity


class TestSpineFieldNamesCanonical:
    def test_tuple_present_and_nonempty(self):
        assert isinstance(Entity.SPINE_FIELD_NAMES, tuple)
        assert len(Entity.SPINE_FIELD_NAMES) > 0

    def test_django_name_mapping_only_for_known_renames(self):
        """SPINE_DJANGO_NAME only carries entries where the serialized
        name and the Django field name differ. Today: only entity_id ↔ id.
        """
        assert "entity_id" in Entity.SPINE_DJANGO_NAME
        assert Entity.SPINE_DJANGO_NAME["entity_id"] == "id"
        # No surprise renames.
        for serialized_name, django_name in Entity.SPINE_DJANGO_NAME.items():
            assert serialized_name != django_name, (
                f"SPINE_DJANGO_NAME entry {serialized_name!r}→{django_name!r} is a "
                f"no-op rename; remove it from the dict."
            )

    def test_every_serialized_name_resolves_to_a_real_django_field(self):
        """Each name in SPINE_FIELD_NAMES must correspond to an actual
        field on the Entity model (after applying SPINE_DJANGO_NAME
        translation)."""
        django_field_names = {f.name for f in Entity._meta.get_fields()}
        for serialized_name in Entity.SPINE_FIELD_NAMES:
            django_name = Entity.SPINE_DJANGO_NAME.get(serialized_name, serialized_name)
            assert django_name in django_field_names, (
                f"SPINE_FIELD_NAMES has {serialized_name!r} (mapped to "
                f"Django field {django_name!r}) which is not a real field "
                f"on Entity. Either add the field to Entity or remove from "
                f"the tuple."
            )

    def test_every_serializable_django_field_appears_in_canonical_tuple(self):
        """Adding a field to Entity without updating SPINE_FIELD_NAMES
        is drift. Catches the reverse direction of the previous test.

        Excludes reverse-FK accessors (the BaseModel one_to_one_rel side)
        and the auto-created HistoricalEntity table reverse-FK — those
        aren't serializable spine fields.
        """
        # Concrete fields only — excludes reverse relations / many-to-many.
        # `concrete_fields` is exactly the columns on the entity table.
        concrete_field_names = {f.name for f in Entity._meta.concrete_fields}

        # Map each Django field name to its envelope-serialized name.
        renamed_djongo_to_serialized = {
            django: serialized
            for serialized, django in Entity.SPINE_DJANGO_NAME.items()
        }
        canonical_django_names = {
            renamed_djongo_to_serialized.get(name, name)
            for name in Entity.SPINE_FIELD_NAMES
        }
        # Reverse-map to find what django names the canonical tuple covers.
        canonical_django_set = {
            Entity.SPINE_DJANGO_NAME.get(name, name)
            for name in Entity.SPINE_FIELD_NAMES
        }

        missing = concrete_field_names - canonical_django_set
        assert not missing, (
            f"Entity has concrete field(s) {sorted(missing)} not listed in "
            f"SPINE_FIELD_NAMES. Either add to the tuple (preserving "
            f"canonical order per spec-grid-entity § Canonical Spine "
            f"Surface) or document why the field is excluded."
        )


class TestSpineFieldNamesOrder:
    def test_entity_id_first(self):
        """entity_id is the stable identifier; conventional order puts it first."""
        assert Entity.SPINE_FIELD_NAMES[0] == "entity_id"

    def test_entity_type_second(self):
        """entity_type is the polymorphism discriminator; comes right after the id."""
        assert Entity.SPINE_FIELD_NAMES[1] == "entity_type"

    def test_name_third(self):
        """name is the human-readable identifier; conventional ordering."""
        assert Entity.SPINE_FIELD_NAMES[2] == "name"
