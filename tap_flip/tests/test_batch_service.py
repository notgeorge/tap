"""Tests for batch service layer."""

import pytest

from tap_flip.batch import (
    batch_context,
    close_batch,
    create_batch,
    fail_batch,
    get_batch,
    get_batch_events,
    get_entity_batches,
    record_batch_event,
)
from tap_flip.history.context import get_batch_id, set_batch_id, set_history_user
from tap_flip.models import BatchEventType, BatchStatus
from tap_grid.models import User
from tap_grid.services import create_entity


@pytest.mark.django_db
class TestCreateBatch:
    """Tests for create_batch function."""

    def test_creates_batch_with_entity(self):
        """create_batch creates a Batch with backing Entity."""
        batch = create_batch(source="test:create")

        assert batch.entity is not None
        assert batch.entity.entity_type == "batch"

    def test_batch_starts_open(self):
        """Created batch has OPEN status."""
        batch = create_batch()

        assert batch.status == BatchStatus.OPEN

    def test_batch_has_source(self):
        """create_batch sets source field."""
        batch = create_batch(source="scanner:aws")

        assert batch.source == "scanner:aws"

    def test_batch_has_actor(self):
        """create_batch can set actor."""
        user = User.objects.create_user(username="batchactor", password="test")
        batch = create_batch(actor=user)

        assert batch.actor == user

    def test_batch_actor_from_context(self):
        """create_batch falls back to context user."""
        user = User.objects.create_user(username="contextactor", password="test")
        set_history_user(user)

        try:
            batch = create_batch()
            assert batch.actor == user
        finally:
            set_history_user(None)

    def test_batch_has_name(self):
        """create_batch sets name on entity."""
        batch = create_batch(name="My Test Batch")

        assert batch.entity.name == "My Test Batch"

    def test_batch_has_metadata(self):
        """create_batch sets metadata."""
        batch = create_batch(metadata={"key": "value"})

        assert batch.metadata == {"key": "value"}


@pytest.mark.django_db
class TestCloseBatch:
    """Tests for close_batch function."""

    def test_close_batch_sets_status_closed(self):
        """close_batch sets status to CLOSED."""
        batch = create_batch()
        close_batch(batch)

        batch.refresh_from_db()
        assert batch.status == BatchStatus.CLOSED

    def test_close_batch_sets_closed_at(self):
        """close_batch sets closed_at timestamp."""
        batch = create_batch()
        assert batch.closed_at is None

        close_batch(batch)
        batch.refresh_from_db()

        assert batch.closed_at is not None

    def test_close_batch_returns_batch(self):
        """close_batch returns the updated batch."""
        batch = create_batch()
        result = close_batch(batch)

        assert result == batch
        assert result.status == BatchStatus.CLOSED

    def test_cannot_close_already_closed_batch(self):
        """close_batch raises ValueError if batch not open."""
        batch = create_batch()
        close_batch(batch)

        with pytest.raises(ValueError, match="Cannot close batch"):
            close_batch(batch)

    def test_cannot_close_failed_batch(self):
        """close_batch raises ValueError if batch is failed."""
        batch = create_batch()
        fail_batch(batch)

        with pytest.raises(ValueError, match="Cannot close batch"):
            close_batch(batch)


@pytest.mark.django_db
class TestFailBatch:
    """Tests for fail_batch function."""

    def test_fail_batch_sets_status_failed(self):
        """fail_batch sets status to FAILED."""
        batch = create_batch()
        fail_batch(batch)

        batch.refresh_from_db()
        assert batch.status == BatchStatus.FAILED

    def test_fail_batch_sets_error_message(self):
        """fail_batch sets error_message."""
        batch = create_batch()
        fail_batch(batch, error_message="Something went wrong")

        batch.refresh_from_db()
        assert batch.error_message == "Something went wrong"

    def test_fail_batch_sets_closed_at(self):
        """fail_batch sets closed_at timestamp."""
        batch = create_batch()
        fail_batch(batch)

        batch.refresh_from_db()
        assert batch.closed_at is not None

    def test_cannot_fail_closed_batch(self):
        """fail_batch raises ValueError if batch not open."""
        batch = create_batch()
        close_batch(batch)

        with pytest.raises(ValueError, match="Cannot fail batch"):
            fail_batch(batch)


@pytest.mark.django_db
class TestBatchContext:
    """Tests for batch_context context manager."""

    def test_context_manager_sets_batch_id(self):
        """batch_context sets batch_id in context."""
        with batch_context() as batch_id:
            assert get_batch_id() == batch_id
            assert len(batch_id) == 36  # UUID format

    def test_context_closes_on_success(self):
        """Batch is closed when context exits normally."""
        with batch_context() as batch_id:
            pass

        batch = get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.CLOSED

    def test_context_fails_on_exception(self):
        """Batch is marked failed when exception raised."""
        batch_id: str = ""
        try:
            with batch_context() as batch_id:
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert batch_id != ""
        batch = get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.FAILED
        assert "Exception during batch execution" in batch.error_message

    def test_context_restores_previous_batch_id(self):
        """Nested contexts restore previous batch_id."""
        set_batch_id("outer-batch-id")

        try:
            with batch_context() as inner_id:
                assert get_batch_id() == inner_id

            # After context, outer should be restored
            assert get_batch_id() == "outer-batch-id"
        finally:
            set_batch_id(None)

    def test_context_with_source(self):
        """batch_context passes source to batch."""
        with batch_context(source="test:context") as batch_id:
            batch = get_batch(batch_id)
            assert batch is not None
            assert batch.source == "test:context"


@pytest.mark.django_db
class TestRecordBatchEvent:
    """Tests for record_batch_event function."""

    def test_records_event_in_batch(self):
        """record_batch_event creates BatchEvent."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("concept", name="Test")
            event = record_batch_event(
                entity=entity,
                event_type=BatchEventType.CREATE,
                model_name="Concept",
            )

            assert event is not None
            assert event.batch == batch
            assert event.event_type == BatchEventType.CREATE
            assert event.entity_id == entity.id
            assert event.model_name == "Concept"
        finally:
            set_batch_id(None)

    def test_returns_none_without_context(self):
        """No event recorded when no batch context."""
        entity = create_entity("concept", name="Test")

        event = record_batch_event(
            entity=entity,
            event_type=BatchEventType.CREATE,
        )

        assert event is None

    def test_explicit_batch_id_overrides_context(self):
        """Explicit batch_id parameter overrides context."""
        batch1 = create_batch(name="Batch 1")
        batch2 = create_batch(name="Batch 2")

        set_batch_id(str(batch1.entity.id))

        try:
            entity = create_entity("concept", name="Test")
            event = record_batch_event(
                entity=entity,
                event_type=BatchEventType.CREATE,
                batch_id=str(batch2.entity.id),  # Override
            )

            assert event is not None
            assert event.batch == batch2
        finally:
            set_batch_id(None)


@pytest.mark.django_db
class TestGetBatch:
    """Tests for get_batch function."""

    def test_retrieves_batch_by_entity_id(self):
        """get_batch retrieves batch by entity ID."""
        batch = create_batch(name="Get Test")
        batch_id = str(batch.entity.id)

        result = get_batch(batch_id)

        assert result is not None
        assert result.id == batch.id

    def test_returns_none_for_invalid_id(self):
        """get_batch returns None for non-existent ID."""
        result = get_batch("00000000-0000-0000-0000-000000000000")

        assert result is None


@pytest.mark.django_db
class TestGetBatchEvents:
    """Tests for get_batch_events function."""

    def test_retrieves_events_for_batch(self):
        """get_batch_events returns events for a batch."""
        batch = create_batch()
        batch_id = str(batch.entity.id)
        set_batch_id(batch_id)

        try:
            entity1 = create_entity("concept", name="Test 1")
            entity2 = create_entity("concept", name="Test 2")

            record_batch_event(entity1, BatchEventType.CREATE, "Concept")
            record_batch_event(entity2, BatchEventType.CREATE, "Concept")

            events = get_batch_events(batch_id)

            assert len(events) == 2
        finally:
            set_batch_id(None)

    def test_returns_empty_for_invalid_batch(self):
        """get_batch_events returns empty list for non-existent batch."""
        events = get_batch_events("00000000-0000-0000-0000-000000000000")

        assert events == []


@pytest.mark.django_db
class TestGetEntityBatches:
    """Tests for get_entity_batches function."""

    def test_retrieves_batches_for_entity(self):
        """get_entity_batches returns batches that affected an entity."""
        batch = create_batch()
        set_batch_id(str(batch.entity.id))

        try:
            entity = create_entity("concept", name="Test")
            record_batch_event(entity, BatchEventType.CREATE, "Concept")

            batches = get_entity_batches(entity.id)

            assert len(batches) == 1
            assert batches[0].id == batch.id
        finally:
            set_batch_id(None)

    def test_returns_empty_for_untracked_entity(self):
        """get_entity_batches returns empty list for entity not in any batch."""
        entity = create_entity("concept", name="Untracked")

        batches = get_entity_batches(entity.id)

        assert batches == []
