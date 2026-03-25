"""Tests for batch signal handlers."""

import pytest

from tap_flip.batch import batch_context, create_batch, get_batch_events
from tap_flip.history.context import get_batch_id, set_batch_id, set_history_user
from tap_flip.models import BatchEventType
from tap_grid.models import User
from tap_grid.services import create_entity
from plugins.lotr.models import Character, Location


@pytest.mark.django_db
class TestPopulateBatchIdSignal:
    """Tests for pre_save signal that populates batch_id."""

    def test_batch_id_populated_on_create(self):
        """batch_id is populated from context on model create."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("character", name="Signal Test")
            character = Character.objects.create(entity=entity, bio="Test")

            assert character.batch_id == str(batch.entity.id)
        finally:
            set_batch_id(None)

    def test_batch_id_not_overwritten_if_set(self):
        """batch_id is not overwritten if already set on instance."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("character", name="Existing ID Test")
            character = Character(entity=entity, bio="Test")
            character.batch_id = "existing-batch-id"
            character.save()

            assert character.batch_id == "existing-batch-id"
        finally:
            set_batch_id(None)

    def test_no_batch_id_without_context(self):
        """FLIP-enabled models raise NoBatchContextError when saved without batch context."""
        from tap_grid.exceptions import NoBatchContextError

        entity = create_entity("character", name="No Context Test")
        with pytest.raises(NoBatchContextError):
            Character.objects.create(entity=entity, bio="Test")

    def test_batch_id_not_set_for_disabled_model(self):
        """batch_id not populated for models with batch tracking disabled."""
        # Location has no FLIP_CONFIG, so batch tracking is disabled
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("location", name="Disabled Test")
            location = Location.objects.create(entity=entity, description="Test")

            # Location inherits batch_id field but signal doesn't populate it
            # because is_batch_enabled(Location) is False
            assert location.batch_id == ""
        finally:
            set_batch_id(None)


@pytest.mark.django_db
class TestRecordSaveEventSignal:
    """Tests for post_save signal that records BatchEvent."""

    def test_create_event_recorded(self):
        """BatchEvent recorded for model creation."""
        batch = create_batch()
        batch_id = str(batch.entity.id)
        set_batch_id(batch_id)

        try:
            entity = create_entity("character", name="Create Event Test")
            Character.objects.create(entity=entity, bio="Test")

            events = get_batch_events(batch_id)
            create_events = [e for e in events if e.event_type == BatchEventType.CREATE]

            assert len(create_events) >= 1
            # Find the event for our character
            character_events = [e for e in create_events if e.entity_type == "character"]
            assert len(character_events) == 1
            assert character_events[0].model_name == "Character"
        finally:
            set_batch_id(None)

    def test_update_event_recorded(self):
        """BatchEvent recorded for model update."""
        batch = create_batch()
        batch_id = str(batch.entity.id)

        # Create inside a setup batch context (FLIP enforcement requires it)
        with batch_context(source="test:setup"):
            entity = create_entity("character", name="Update Event Test")
            character = Character.objects.create(entity=entity, bio="Original")

        # Update inside batch context
        set_batch_id(batch_id)
        try:
            character.bio = "Updated"
            character.save()

            events = get_batch_events(batch_id)
            update_events = [e for e in events if e.event_type == BatchEventType.UPDATE]

            assert len(update_events) == 1
            assert update_events[0].entity_id == entity.id
        finally:
            set_batch_id(None)

    def test_no_event_without_context(self):
        """FLIP-enabled models raise NoBatchContextError instead of silently skipping events."""
        from tap_grid.exceptions import NoBatchContextError

        entity = create_entity("character", name="No Event Test")
        with pytest.raises(NoBatchContextError):
            Character.objects.create(entity=entity, bio="Test")


@pytest.mark.django_db
class TestRecordDeleteEventSignal:
    """Tests for post_delete signal that records BatchEvent."""

    def test_delete_event_recorded(self):
        """BatchEvent recorded for model deletion."""
        batch = create_batch()
        batch_id = str(batch.entity.id)

        # Create inside a setup batch context (FLIP enforcement requires it)
        with batch_context(source="test:setup"):
            entity = create_entity("character", name="Delete Event Test")
            Character.objects.create(entity=entity, bio="To Delete")
        entity_id = entity.id

        # Delete inside batch context
        set_batch_id(batch_id)
        try:
            # Delete the character (entity deletion cascades)
            entity.delete()

            events = get_batch_events(batch_id)
            delete_events = [e for e in events if e.event_type == BatchEventType.DELETE]

            assert len(delete_events) == 1
            assert delete_events[0].entity_id == entity_id
        finally:
            set_batch_id(None)


@pytest.mark.django_db
class TestSignalActorAttribution:
    """Tests for actor attribution in signal handlers."""

    def test_actor_from_context(self):
        """BatchEvent actor comes from history context."""
        user = User.objects.create_user(username="signalactor", password="test")
        set_history_user(user)

        batch = create_batch()
        batch_id = str(batch.entity.id)
        set_batch_id(batch_id)

        try:
            entity = create_entity("character", name="Actor Test")
            Character.objects.create(entity=entity, bio="Test")

            events = get_batch_events(batch_id)
            character_events = [e for e in events if e.entity_type == "character"]

            assert len(character_events) == 1
            assert character_events[0].actor == user
        finally:
            set_batch_id(None)
            set_history_user(None)


@pytest.mark.django_db
class TestBatchContextIntegration:
    """Integration tests for batch_context with signals."""

    def test_full_flow_with_context_manager(self):
        """Full flow: batch_context -> create models -> events recorded."""
        with batch_context(source="integration:test") as batch_id:
            entity = create_entity("character", name="Integration Test")
            character = Character.objects.create(entity=entity, bio="Test")

            # batch_id should be populated on model
            assert character.batch_id == batch_id

        # Events should be recorded
        events = get_batch_events(batch_id)
        character_events = [e for e in events if e.entity_type == "character"]

        assert len(character_events) == 1
        assert character_events[0].event_type == BatchEventType.CREATE

    def test_multiple_models_in_batch(self):
        """Multiple models created in same batch all get tracked."""
        with batch_context(source="multi:test") as batch_id:
            for i in range(3):
                entity = create_entity("character", name=f"Character {i}")
                Character.objects.create(entity=entity, bio=f"Bio {i}")

        events = get_batch_events(batch_id)
        character_events = [e for e in events if e.entity_type == "character"]

        assert len(character_events) == 3

    def test_batch_id_cleared_after_context(self):
        """batch_id context is cleared after context manager exits."""
        with batch_context() as batch_id:
            assert get_batch_id() == batch_id

        assert get_batch_id() is None
