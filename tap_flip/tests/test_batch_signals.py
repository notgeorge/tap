"""Tests for CallerContext-based provenance recording.

Replaces the old signal-based tests (tap_flip.batch.signals has been removed).
Provenance is now driven by CallerContext flowing through BaseModel.save().
See req-grid-service-batch-signals, req-grid-service-batch-infra.
"""

import uuid

import pytest

from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.exceptions import NoBatchContextError
from tap_grid.services import create_entity
from plugins.lotr.models import Character, Location


@pytest.mark.django_db
class TestCallerContextBatchIdPropagation:
    """CallerContext batch_id is stamped onto model instance and flip_map on save."""

    def test_batch_id_populated_from_caller_context(self):
        """batch_id field on model is set from CallerContext when saving."""
        batch_id = str(uuid.uuid7())
        set_caller_context(CallerContext(user=None, batch_id=batch_id))
        try:
            entity = create_entity("character", name="CallerContext Test")
            character = Character.objects.create(entity=entity, bio="Test")
            assert character.batch_id == batch_id
        finally:
            set_caller_context(None)

    def test_batch_id_overwrites_previous_on_save(self):
        """CallerContext batch_id always stamps the model, reflecting the latest write."""
        first_batch = str(uuid.uuid7())
        second_batch = str(uuid.uuid7())

        set_caller_context(CallerContext(user=None, batch_id=first_batch))
        try:
            entity = create_entity("character", name="Overwrite Test")
            character = Character.objects.create(entity=entity, bio="Original")
        finally:
            set_caller_context(None)

        assert character.batch_id == first_batch

        set_caller_context(CallerContext(user=None, batch_id=second_batch))
        try:
            character.bio = "Updated"
            character.save()
        finally:
            set_caller_context(None)

        assert character.batch_id == second_batch

    def test_flip_map_updated_from_caller_context(self):
        """flip_map is populated with batch_id from CallerContext."""
        batch_id = str(uuid.uuid7())
        set_caller_context(CallerContext(user=None, batch_id=batch_id))
        try:
            entity = create_entity("character", name="FlipMap Test")
            character = Character.objects.create(entity=entity, bio="Test")
        finally:
            set_caller_context(None)

        # Character has FLIP enabled; flip_map should record the batch_id
        assert character.flip_map != {}
        for field_batch_id in character.flip_map.values():
            assert field_batch_id == batch_id

    def test_no_caller_context_raises_for_flip_enabled_model(self):
        """FLIP-enabled models raise NoBatchContextError when saved without CallerContext."""
        set_caller_context(None)
        entity = create_entity("character", name="No Context Test")
        with pytest.raises(NoBatchContextError):
            Character.objects.create(entity=entity, bio="Test")

    def test_no_caller_context_succeeds_for_flip_disabled_model(self):
        """FLIP-disabled models save successfully without CallerContext."""
        set_caller_context(None)
        entity = create_entity("location", name="No Context Location")
        # Location has no FLIP_CONFIG — should not raise
        location = Location.objects.create(entity=entity, description="Test")
        assert location.batch_id == ""

    def test_flip_disabled_model_ignores_caller_context_batch_id(self):
        """FLIP-disabled model batch_id field is still stamped from CallerContext."""
        batch_id = str(uuid.uuid7())
        set_caller_context(CallerContext(user=None, batch_id=batch_id))
        try:
            entity = create_entity("location", name="Location Context Test")
            location = Location.objects.create(entity=entity, description="Test")
        finally:
            set_caller_context(None)

        # batch_id is stamped on all BaseModel instances when CallerContext is present
        assert location.batch_id == batch_id
        # But flip_map stays empty for FLIP-disabled models
        assert location.flip_map == {}

    def test_get_caller_context_round_trips(self):
        """set_caller_context / get_caller_context are symmetric."""
        ctx = CallerContext(user=None, batch_id="test-batch-id")
        set_caller_context(ctx)
        try:
            assert get_caller_context() is ctx
        finally:
            set_caller_context(None)
        assert get_caller_context() is None

    def test_caller_context_is_frozen(self):
        """CallerContext is immutable after creation."""
        from dataclasses import FrozenInstanceError

        ctx = CallerContext(user=None, batch_id="test")
        with pytest.raises(FrozenInstanceError):
            ctx.batch_id = "other"  # type: ignore[misc]
