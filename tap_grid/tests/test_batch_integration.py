"""Integration tests for batch and history tracking.

Tests the full flow: context → model save → history recording.
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model

from tap_grid.batch import create_batch
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.history import get_historical_records, is_history_enabled, set_history_user
from tap_grid.services import create_entity

User = get_user_model()


@contextmanager
def _batch_ctx(source: str = "test") -> Generator[str]:
    """Test helper: create a Batch entity and set CallerContext for the duration."""
    batch = create_batch(source=source)
    batch_id = str(batch.entity.id)
    prev = get_caller_context()
    set_caller_context(CallerContext(user=get_caller_context().user, batch_id=batch_id))
    try:
        yield batch_id
    finally:
        set_caller_context(prev)


@pytest.mark.django_db
class TestFullHistoryFlow:
    """End-to-end tests for history tracking flow."""

    def test_create_update_history_flow(self):
        """Full flow: create → update → history records increase."""
        from tap_plugin.lotr.models import Character

        user = User.objects.create_user(username="flowtest", password="test")
        set_history_user(user)
        try:
            with _batch_ctx(source="test:history-create"):
                entity = create_entity("character", name="Frodo Baggins")
                character = Character.objects.create(entity=entity, bio="A hobbit.")

            with _batch_ctx(source="test:history-update"):
                character.bio = "A brave hobbit of the Shire."
                character.save()

            records = list(get_historical_records(character))
            assert len(records) == 2  # Create + Update
        finally:
            set_history_user(None)

    def test_history_preserves_old_values(self):
        """History records preserve the state at each point in time."""
        from tap_plugin.lotr.models import Character

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

    def test_history_records_user_from_context(self):
        """History records the user from context."""
        from tap_plugin.lotr.models import Character

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
        from tap_plugin.lotr.models import Character

        set_history_user(None)

        with _batch_ctx(source="test:history-no-user"):
            entity = create_entity("character", name="No User Test")
            character = Character.objects.create(entity=entity, bio="Test")

        latest_record = character.history.latest("history_id")
        assert latest_record.history_user is None


@pytest.mark.django_db
class TestBatchIdFieldExists:
    """Tests for batch_id field on BaseModel."""

    def test_batch_id_field_exists_on_character(self):
        """Character model has batch_id field populated by CallerContext."""
        from tap_plugin.lotr.models import Character

        with _batch_ctx(source="test:batch-id") as batch_id:
            entity = create_entity("character", name="Batch ID Test")
            character = Character.objects.create(entity=entity, bio="Test")

        assert hasattr(character, "batch_id")
        assert character.batch_id == batch_id

    def test_batch_id_updated_on_subsequent_save(self):
        """batch_id field is updated to the latest CallerContext batch on each save."""
        from tap_plugin.lotr.models import Character

        with _batch_ctx(source="test:batch-id-create") as first_batch_id:
            entity = create_entity("character", name="Batch Set Test")
            character = Character.objects.create(entity=entity, bio="Test")

        second_batch_id = str(uuid.uuid7())
        set_caller_context(CallerContext(user=get_caller_context().user, batch_id=second_batch_id))
        try:
            character.bio = "Updated"
            character.save()
        finally:
            set_caller_context(None)

        character.refresh_from_db()
        assert character.batch_id == second_batch_id
        assert character.batch_id != first_batch_id


@pytest.mark.django_db
class TestHistoryEnabledForAllModels:
    """All concrete BaseModel subclasses now have history enabled by default."""

    def test_character_has_history(self):
        """Character has history (FLIP-enabled model)."""
        from tap_plugin.lotr.models import Character

        assert is_history_enabled(Character) is True

    def test_location_has_history(self):
        """Location has history too (all BaseModel subclasses inherit it)."""
        from tap_plugin.lotr.models import Location

        assert is_history_enabled(Location) is True

    def test_both_have_history_manager(self):
        """Both Character and Location have the history manager attribute."""
        from tap_plugin.lotr.models import Character, Location

        assert hasattr(Character, "history")
        assert hasattr(Location, "history")


@pytest.mark.django_db
class TestPerOperationCapability:
    """A write capability does not carry a delete (req-tap-auth-policy per-op).

    End-to-end (through the real `delete_node` verb, not the backstop primitive):
    an actor holding `grid.write` but not `grid.delete` is denied a delete. This
    proves the per-op split is enforced at the service boundary, and that the
    denial is delete-specific — the same actor IS authorized to write.
    """

    def _write_only_user(self) -> object:
        from django.contrib.auth.models import Group, Permission

        from tap_auth import sync

        sync.sync_auth()
        group, _ = Group.objects.get_or_create(name="test_write_only")
        group.permissions.set([Permission.objects.get(codename="grid_write")])
        user = User.objects.create_user(username="write-only", password="x")
        user.groups.add(group)
        return user

    def test_write_only_actor_is_denied_delete(self):
        from tap_auth import policy
        from tap_auth.errors import CapabilityDenied
        from tap_grid.services import delete_node

        ctx = CallerContext(user=self._write_only_user())
        # Sanity: the actor genuinely holds write but not delete — so a delete
        # denial below is about the operation class, not a blanket no-caps actor.
        assert policy.can(ctx, "grid.write") is True
        assert policy.can(ctx, "grid.delete") is False

        # The denial fires in the decorator's authorize(), before any DB work, so
        # a real seeded node is unnecessary — the gate never reaches the body.
        with pytest.raises(CapabilityDenied):
            delete_node(uuid.uuid4(), caller_context=ctx)
