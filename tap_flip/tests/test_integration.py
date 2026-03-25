"""Integration tests for FLIP Phase 1 (history tracking).

Tests the full flow: context → model save → history recording.
"""

import pytest

from tap_flip.config import is_history_enabled
from tap_flip.history import get_historical_records, get_history_timeline, set_history_user
from tap_grid.models import User
from tap_grid.services import create_entity
from plugins.lotr.models import Character, Location


@pytest.mark.django_db
class TestFullHistoryFlow:
    """End-to-end tests for history tracking flow."""

    def test_create_update_history_flow(self):
        """Full flow: create → update → query history."""
        from tap_flip.batch.service import batch_context

        user = User.objects.create_user(username="flowtest", password="test")
        set_history_user(user)
        try:
            with batch_context(source="test:history-create"):
                entity = create_entity("character", name="Frodo Baggins")
                character = Character.objects.create(entity=entity, bio="A hobbit.")

            with batch_context(source="test:history-update"):
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
        from tap_flip.batch.service import batch_context

        with batch_context(source="test:history-v1"):
            entity = create_entity("character", name="Gandalf")
            character = Character.objects.create(entity=entity, bio="Version 1")

        with batch_context(source="test:history-v2"):
            character.bio = "Version 2"
            character.save()

        with batch_context(source="test:history-v3"):
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
        """Character model has batch_id field populated by batch context."""
        from tap_flip.batch.service import batch_context

        with batch_context(source="test:batch-id"):
            entity = create_entity("character", name="Batch ID Test")
            character = Character.objects.create(entity=entity, bio="Test")

        assert hasattr(character, "batch_id")
        assert character.batch_id != ""  # signal populates it from batch context

    def test_batch_id_can_be_set(self):
        """batch_id field can be manually overwritten."""
        from tap_flip.batch.service import batch_context

        with batch_context(source="test:batch-id-create"):
            entity = create_entity("character", name="Batch Set Test")
            character = Character.objects.create(entity=entity, bio="Test")

        batch_uuid = "019468b7-1234-7def-8000-000000000001"
        character.batch_id = batch_uuid
        with batch_context(source="test:batch-id-update"):
            character.save()

        character.refresh_from_db()
        assert character.batch_id == batch_uuid

    def test_batch_id_field_exists_on_location(self):
        """Location model also has batch_id field (inherited from BaseModel)."""
        entity = create_entity("location", name="Location Batch Test")
        location = Location.objects.create(entity=entity, description="Test location")

        assert hasattr(location, "batch_id")
        assert location.batch_id == ""


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
        """Both Character and Location have batch_id (BaseModel field)."""
        from tap_flip.batch.service import batch_context

        character_entity = create_entity("character", name="C")
        location_entity = create_entity("location", name="L")

        with batch_context(source="test:batch-id-both"):
            character = Character.objects.create(entity=character_entity, bio="Test")
        location = Location.objects.create(entity=location_entity, description="Test")

        assert hasattr(character, "batch_id")
        assert hasattr(location, "batch_id")
