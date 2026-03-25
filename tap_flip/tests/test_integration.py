"""Integration tests for FLIP Phase 1 (history tracking).

Tests the full flow: context → model save → history recording.
"""

import uuid
from contextlib import contextmanager
from collections.abc import Generator

import pytest

from tap_flip.config import is_history_enabled
from tap_flip.history import get_historical_records, get_history_timeline, set_history_user
from tap_flip.batch.service import create_batch
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.models import User
from tap_grid.services import create_entity
from plugins.lotr.models import Character, Location


@contextmanager
def _batch_ctx(source: str = "test") -> Generator[str, None, None]:
    """Test helper: create a Batch entity and set CallerContext for the duration.

    Replaces the removed batch_context() context manager for test use.
    The Batch entity is created so BatchEvent queries remain valid.
    """
    batch = create_batch(source=source)
    batch_id = str(batch.entity.id)
    prev = get_caller_context()
    set_caller_context(CallerContext(user=None, batch_id=batch_id))
    try:
        yield batch_id
    finally:
        set_caller_context(prev)


@pytest.mark.django_db
class TestFullHistoryFlow:
    """End-to-end tests for history tracking flow."""

    def test_create_update_history_flow(self):
        """Full flow: create → update → query history."""
        user = User.objects.create_user(username="flowtest", password="test")
        set_history_user(user)
        try:
            with _batch_ctx(source="test:history-create"):
                entity = create_entity("character", name="Frodo Baggins")
                character = Character.objects.create(entity=entity, bio="A hobbit.")

            with _batch_ctx(source="test:history-update"):
                character.bio = "A brave hobbit of the Shire."
                character.save()

            records = get_historical_records(character)
            timeline = get_history_timeline(character)

            assert records.count() == 2  # Create + Update
            assert len(timeline) == 2
            assert timeline[0]["actor"] == "flowtest"
        finally:
            set_history_user(None)

    def test_history_preserves_old_values(self):
        """History records preserve the state at each point in time."""
        with _batch_ctx(source="test:history-v1"):
            entity = create_entity("character", name="Gandalf")
            character = Character.objects.create(entity=entity, bio="Version 1")

        with _batch_ctx(source="test:history-v2"):
            character.bio = "Version 2"
            character.save()

        with _batch_ctx(source="test:history-v3"):
            character.bio = "Version 3"
            character.save()

        records = list(character.history.all().order_by("history_date"))

        assert len(records) == 3
        assert records[0].bio == "Version 1"
        assert records[1].bio == "Version 2"
        assert records[2].bio == "Version 3"


@pytest.mark.django_db
class TestBatchIdFieldExists:
    """Tests for batch_id field on BaseModel."""

    def test_batch_id_field_exists_on_character(self):
        """Character model has batch_id field populated by CallerContext."""
        with _batch_ctx(source="test:batch-id") as batch_id:
            entity = create_entity("character", name="Batch ID Test")
            character = Character.objects.create(entity=entity, bio="Test")

        assert hasattr(character, "batch_id")
        assert character.batch_id == batch_id

    def test_batch_id_updated_on_subsequent_save(self):
        """batch_id field is updated to the latest CallerContext batch on each save."""
        with _batch_ctx(source="test:batch-id-create") as first_batch_id:
            entity = create_entity("character", name="Batch Set Test")
            character = Character.objects.create(entity=entity, bio="Test")

        second_batch_id = str(uuid.uuid7())
        set_caller_context(CallerContext(user=None, batch_id=second_batch_id))
        try:
            character.bio = "Updated"
            character.save()
        finally:
            set_caller_context(None)

        character.refresh_from_db()
        assert character.batch_id == second_batch_id
        assert character.batch_id != first_batch_id

    def test_batch_id_field_exists_on_location(self):
        """Location model also has batch_id field (inherited from BaseModel).

        batch_id is stamped from CallerContext even on FLIP-disabled models —
        the field tracks which batch last touched the record.
        """
        entity = create_entity("location", name="Location Batch Test")
        location = Location.objects.create(entity=entity, description="Test location")

        assert hasattr(location, "batch_id")
        # batch_id is populated from the active CallerContext (auto-fixture provides one)
        assert location.batch_id != ""


@pytest.mark.django_db
class TestHistoryEnabledVsDisabled:
    """Tests contrasting history-enabled vs disabled models."""

    def test_character_enabled_location_disabled(self):
        """Character has history, Location does not."""
        assert is_history_enabled(Character) is True
        assert is_history_enabled(Location) is False

    def test_character_has_history_manager(self):
        """Character has the history manager."""
        assert hasattr(Character, "history")

    def test_location_no_history_manager(self):
        """Location does not have history manager; get_historical_records returns empty."""
        entity = create_entity("location", name="No History Test")
        location = Location.objects.create(entity=entity, description="Test")

        records = get_historical_records(location)
        assert len(records) == 0

    def test_both_have_batch_id(self):
        """Both Character and Location have batch_id (BaseModel field).

        batch_id is stamped on all BaseModel instances when a CallerContext is active.
        """
        character_entity = create_entity("character", name="C")
        location_entity = create_entity("location", name="L")

        with _batch_ctx(source="test:batch-id-both") as batch_id:
            character = Character.objects.create(entity=character_entity, bio="Test")
        location = Location.objects.create(entity=location_entity, description="Test")

        assert hasattr(character, "batch_id")
        assert character.batch_id == batch_id
        assert hasattr(location, "batch_id")
        assert location.batch_id != ""  # stamped from auto CallerContext fixture
