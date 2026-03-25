"""Tests for history service layer."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest

from tap_flip.batch.service import create_batch
from tap_flip.config import is_history_enabled
from tap_flip.history.context import set_history_user
from tap_flip.history.service import get_historical_records, get_history_timeline
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.models import User
from tap_grid.services import create_entity
from plugins.lotr.models import Character, Location


@contextmanager
def _batch_ctx(source: str = "test") -> Generator[str, None, None]:
    """Create a Batch entity and set CallerContext for the duration (test helper)."""
    batch = create_batch(source=source)
    batch_id = str(batch.entity.id)
    prev = get_caller_context()
    set_caller_context(CallerContext(user=None, batch_id=batch_id))
    try:
        yield batch_id
    finally:
        set_caller_context(prev)


@pytest.mark.django_db
class TestHistoryEnabled:
    """Tests for history enablement on models."""

    def test_character_has_history_enabled(self):
        """Character model has history tracking enabled via FLIP_CONFIG."""
        assert is_history_enabled(Character) is True

    def test_location_has_history_disabled(self):
        """Location model has history disabled (default)."""
        assert is_history_enabled(Location) is False

    def test_character_has_history_manager(self):
        """Character has the history manager from django-simple-history."""
        assert hasattr(Character, "history")


@pytest.mark.django_db
class TestGetHistoricalRecords:
    """Tests for get_historical_records function."""

    def test_new_character_has_creation_record(self):
        """New Character instance has at least one history record (creation)."""
        with _batch_ctx(source="test:history"):
            entity = create_entity("character", name="Test Character")
            character = Character.objects.create(entity=entity, bio="Initial bio")

        records = get_historical_records(character)
        assert records.count() >= 1

    def test_update_creates_new_record(self):
        """Updating a Character creates a new history record."""
        with _batch_ctx(source="test:history-create"):
            entity = create_entity("character", name="Update Test")
            character = Character.objects.create(entity=entity, bio="Original")
        initial_count = character.history.count()

        with _batch_ctx(source="test:history-update"):
            character.bio = "Updated bio"
            character.save()

        records = get_historical_records(character)
        assert records.count() > initial_count

    def test_history_disabled_returns_empty(self):
        """get_historical_records returns empty for disabled models."""
        entity = create_entity("location", name="Test Location")
        location = Location.objects.create(entity=entity, description="Some place")

        records = get_historical_records(location)
        assert len(records) == 0


@pytest.mark.django_db
class TestGetHistoryTimeline:
    """Tests for get_history_timeline function."""

    def test_timeline_has_required_fields(self):
        """Timeline entries have timestamp, change_type, actor, record_id."""
        with _batch_ctx(source="test:history"):
            entity = create_entity("character", name="Timeline Test")
            character = Character.objects.create(entity=entity, bio="Test")

        timeline = get_history_timeline(character)
        assert len(timeline) >= 1

        entry = timeline[0]
        assert "timestamp" in entry
        assert "change_type" in entry
        assert "actor" in entry
        assert "record_id" in entry

    def test_timeline_records_change_types(self):
        """Timeline shows different change types for create/update."""
        with _batch_ctx(source="test:history-create"):
            entity = create_entity("character", name="Change Type Test")
            character = Character.objects.create(entity=entity, bio="Original")

        with _batch_ctx(source="test:history-update"):
            character.bio = "Updated"
            character.save()

        timeline = get_history_timeline(character)
        change_types = [e["change_type"] for e in timeline]
        assert "Changed" in change_types or "Created" in change_types


@pytest.mark.django_db
class TestHistoryUserAttribution:
    """Tests for user attribution in history records."""

    def test_history_records_user_from_context(self):
        """History records the user from context."""
        user = User.objects.create_user(username="historian", password="test")
        set_history_user(user)

        with _batch_ctx(source="test:history-user"):
            entity = create_entity("character", name="User Test")
            character = Character.objects.create(entity=entity, bio="Test")

        latest_record = character.history.latest("history_id")
        assert latest_record.history_user == user

        set_history_user(None)

    def test_history_without_user_context(self):
        """History works even without user in context (None)."""
        set_history_user(None)

        with _batch_ctx(source="test:history-no-user"):
            entity = create_entity("character", name="No User Test")
            character = Character.objects.create(entity=entity, bio="Test")

        latest_record = character.history.latest("history_id")
        assert latest_record.history_user is None
