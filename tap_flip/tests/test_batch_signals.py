"""Tests for batch signal handlers."""

import pytest

from tap_flip.batch import batch_context, create_batch, get_batch_events
from tap_flip.history.context import get_batch_id, set_batch_id, set_history_user
from tap_flip.models import BatchEventType
from tap_grid.models import User
from tap_grid.services import create_entity
from plugins.core_examples.models import Concept, Precept


@pytest.mark.django_db
class TestPopulateBatchIdSignal:
    """Tests for pre_save signal that populates batch_id."""

    def test_batch_id_populated_on_create(self):
        """batch_id is populated from context on model create."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("concept", name="Signal Test")
            concept = Concept.objects.create(entity=entity, summary="Test")

            assert concept.batch_id == str(batch.entity.id)
        finally:
            set_batch_id(None)

    def test_batch_id_not_overwritten_if_set(self):
        """batch_id is not overwritten if already set on instance."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("concept", name="Existing ID Test")
            concept = Concept(entity=entity, summary="Test")
            concept.batch_id = "existing-batch-id"
            concept.save()

            assert concept.batch_id == "existing-batch-id"
        finally:
            set_batch_id(None)

    def test_no_batch_id_without_context(self):
        """batch_id remains empty without batch context."""
        entity = create_entity("concept", name="No Context Test")
        concept = Concept.objects.create(entity=entity, summary="Test")

        assert concept.batch_id == ""

    def test_batch_id_not_set_for_disabled_model(self):
        """batch_id not populated for models with batch tracking disabled."""
        # Precept has batch tracking disabled (default FLIP_CONFIG)
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("precept", name="Disabled Test")
            precept = Precept.objects.create(entity=entity, statement="Test")

            # Precept inherits batch_id field but signal doesn't populate it
            # because is_batch_enabled(Precept) is False
            assert precept.batch_id == ""
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
            entity = create_entity("concept", name="Create Event Test")
            Concept.objects.create(entity=entity, summary="Test")

            events = get_batch_events(batch_id)
            create_events = [e for e in events if e.event_type == BatchEventType.CREATE]

            assert len(create_events) >= 1
            # Find the event for our concept
            concept_events = [e for e in create_events if e.entity_type == "concept"]
            assert len(concept_events) == 1
            assert concept_events[0].model_name == "Concept"
        finally:
            set_batch_id(None)

    def test_update_event_recorded(self):
        """BatchEvent recorded for model update."""
        batch = create_batch()
        batch_id = str(batch.entity.id)

        # Create outside batch context
        entity = create_entity("concept", name="Update Event Test")
        concept = Concept.objects.create(entity=entity, summary="Original")

        # Update inside batch context
        set_batch_id(batch_id)
        try:
            concept.summary = "Updated"
            concept.save()

            events = get_batch_events(batch_id)
            update_events = [e for e in events if e.event_type == BatchEventType.UPDATE]

            assert len(update_events) == 1
            assert update_events[0].entity_id == entity.id
        finally:
            set_batch_id(None)

    def test_no_event_without_context(self):
        """No BatchEvent recorded without batch context."""
        entity = create_entity("concept", name="No Event Test")
        Concept.objects.create(entity=entity, summary="Test")

        # No batch context, so no events to query
        # Just verify no error occurred


@pytest.mark.django_db
class TestRecordDeleteEventSignal:
    """Tests for post_delete signal that records BatchEvent."""

    def test_delete_event_recorded(self):
        """BatchEvent recorded for model deletion."""
        batch = create_batch()
        batch_id = str(batch.entity.id)

        # Create outside batch context
        entity = create_entity("concept", name="Delete Event Test")
        Concept.objects.create(entity=entity, summary="To Delete")
        entity_id = entity.id

        # Delete inside batch context
        set_batch_id(batch_id)
        try:
            # Delete the concept (entity deletion cascades)
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
            entity = create_entity("concept", name="Actor Test")
            Concept.objects.create(entity=entity, summary="Test")

            events = get_batch_events(batch_id)
            concept_events = [e for e in events if e.entity_type == "concept"]

            assert len(concept_events) == 1
            assert concept_events[0].actor == user
        finally:
            set_batch_id(None)
            set_history_user(None)


@pytest.mark.django_db
class TestBatchContextIntegration:
    """Integration tests for batch_context with signals."""

    def test_full_flow_with_context_manager(self):
        """Full flow: batch_context -> create models -> events recorded."""
        with batch_context(source="integration:test") as batch_id:
            entity = create_entity("concept", name="Integration Test")
            concept = Concept.objects.create(entity=entity, summary="Test")

            # batch_id should be populated on model
            assert concept.batch_id == batch_id

        # Events should be recorded
        events = get_batch_events(batch_id)
        concept_events = [e for e in events if e.entity_type == "concept"]

        assert len(concept_events) == 1
        assert concept_events[0].event_type == BatchEventType.CREATE

    def test_multiple_models_in_batch(self):
        """Multiple models created in same batch all get tracked."""
        with batch_context(source="multi:test") as batch_id:
            for i in range(3):
                entity = create_entity("concept", name=f"Concept {i}")
                Concept.objects.create(entity=entity, summary=f"Summary {i}")

        events = get_batch_events(batch_id)
        concept_events = [e for e in events if e.entity_type == "concept"]

        assert len(concept_events) == 3

    def test_batch_id_cleared_after_context(self):
        """batch_id context is cleared after context manager exits."""
        with batch_context() as batch_id:
            assert get_batch_id() == batch_id

        assert get_batch_id() is None
