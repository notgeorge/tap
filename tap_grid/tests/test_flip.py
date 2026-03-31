"""Tests for FLIP field-path map logic (tap_grid.flip)."""

import itertools
import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest

from tap_grid.batch_service import create_batch
from tap_grid.flip import clear_registry
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.context import set_batch_id
from tap_grid.exceptions import NoBatchContextError
from tap_grid.flip import update_flip_map


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

_counter = itertools.count()


def make_instance(flip_config=None):
    """Create a fake BaseModel-like instance with a unique class name.

    Uses a counter to ensure each call produces a distinct class name,
    preventing FLIP config caching from bleeding between tests.
    """
    cls = type(f"FakeModel_{next(_counter)}", (), {"FLIP_CONFIG": flip_config or {}})
    instance = object.__new__(cls)
    instance.flip_map = {}
    return instance


@pytest.fixture(autouse=True)
def reset_context_and_registry():
    """Clear batch context and FLIP registry between tests."""
    set_batch_id(None)
    clear_registry()
    yield
    set_batch_id(None)
    clear_registry()


class TestUpdateFlipMapNoOp:
    """update_flip_map is a no-op when FLIP is not enabled."""

    def test_returns_false_when_flip_disabled(self):
        instance = make_instance({"flip": {"enabled": False, "fields": ["status"]}})
        assert update_flip_map(instance, ["status"], "batch-123") is False

    def test_returns_false_when_no_flip_config(self):
        instance = make_instance({})
        assert update_flip_map(instance, ["status"], "batch-123") is False

    def test_returns_false_when_no_tracked_fields(self):
        instance = make_instance({"flip": {"enabled": True, "fields": []}})
        assert update_flip_map(instance, ["status"], "batch-123") is False

    def test_no_mutation_when_disabled(self):
        instance = make_instance({"flip": {"enabled": False, "fields": ["status"]}})
        update_flip_map(instance, ["status"], "batch-123")
        assert instance.flip_map == {}


class TestUpdateFlipMapEnforcesBatch:
    """NoBatchContextError is raised when FLIP is enabled but no batch is provided."""

    def test_raises_when_flip_enabled_and_no_batch(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status"]}})
        with pytest.raises(NoBatchContextError):
            update_flip_map(instance, ["status"], None)

    def test_does_not_raise_when_flip_disabled_and_no_batch(self):
        """Non-FLIP models are unaffected even without a batch."""
        instance = make_instance({"flip": {"enabled": False, "fields": ["status"]}})
        result = update_flip_map(instance, ["status"], None)
        assert result is False


class TestUpdateFlipMapPartialSave:
    """update_flip_map stamps only fields in both changed_fields and the tracked list."""

    def test_stamps_tracked_changed_field(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status", "name"]}})
        result = update_flip_map(instance, ["status"], "batch-abc")
        assert result is True
        assert instance.flip_map == {"status": "batch-abc"}

    def test_ignores_untracked_changed_fields(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status"]}})
        result = update_flip_map(instance, ["name", "description"], "batch-abc")
        assert result is False
        assert instance.flip_map == {}

    def test_stamps_multiple_tracked_fields(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["a", "b", "c"]}})
        update_flip_map(instance, ["a", "b"], "batch-xyz")
        assert instance.flip_map == {"a": "batch-xyz", "b": "batch-xyz"}

    def test_returns_false_when_no_overlap(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status"]}})
        result = update_flip_map(instance, ["name"], "batch-abc")
        assert result is False


class TestUpdateFlipMapFullSave:
    """When changed_fields is None (full save), all tracked fields are stamped."""

    def test_stamps_all_tracked_fields_on_full_save(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["a", "b"]}})
        result = update_flip_map(instance, None, "batch-full")
        assert result is True
        assert instance.flip_map == {"a": "batch-full", "b": "batch-full"}


class TestUpdateFlipMapOverwrite:
    """Subsequent writes overwrite prior batch IDs for the same field."""

    def test_overwrites_previous_batch_id(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status"]}})
        instance.flip_map = {"status": "old-batch"}
        update_flip_map(instance, ["status"], "new-batch")
        assert instance.flip_map["status"] == "new-batch"

    def test_preserves_unrelated_flip_entries(self):
        instance = make_instance({"flip": {"enabled": True, "fields": ["status", "name"]}})
        instance.flip_map = {"name": "prior-batch"}
        update_flip_map(instance, ["status"], "new-batch")
        assert instance.flip_map["name"] == "prior-batch"
        assert instance.flip_map["status"] == "new-batch"


@pytest.mark.django_db
class TestUpdateFlipMapIntegration:
    """Integration: flip_map is persisted atomically with the save."""

    def test_flip_map_written_on_create(self, monkeypatch):
        """A FLIP-enabled model save writes flip_map to the database."""
        from plugins.lotr.models import Character
        from tap_grid.services import create_entity

        monkeypatch.setattr(
            Character,
            "FLIP_CONFIG",
            {"batch": {"enabled": True}, "flip": {"enabled": True, "fields": ["bio"]}},
        )
        clear_registry()

        with _batch_ctx(source="test:flip") as batch_id:
            entity = create_entity("character", name="Frodo")
            char = Character.objects.create(entity=entity, bio="A hobbit")

        char.refresh_from_db()
        assert char.flip_map.get("bio") == batch_id

    def test_flip_map_updated_on_partial_save(self, monkeypatch):
        """Partial save (update_fields) stamps only the changed tracked field."""
        from plugins.lotr.models import Character
        from tap_grid.services import create_entity

        monkeypatch.setattr(
            Character,
            "FLIP_CONFIG",
            {"batch": {"enabled": True}, "flip": {"enabled": True, "fields": ["bio"]}},
        )
        clear_registry()

        with _batch_ctx(source="test:flip-create"):
            entity = create_entity("character", name="Sam")
            char = Character.objects.create(entity=entity, bio="A gardener")

        with _batch_ctx(source="test:flip-update") as batch_id2:
            char.bio = "Gardener of the Shire"
            char.save(update_fields=["bio"])

        char.refresh_from_db()
        assert char.flip_map.get("bio") == batch_id2

    def test_untracked_field_not_in_flip_map(self, monkeypatch):
        """Fields not in the tracked list are absent from flip_map after save."""
        from plugins.lotr.models import Character
        from tap_grid.services import create_entity

        monkeypatch.setattr(
            Character,
            "FLIP_CONFIG",
            {"batch": {"enabled": True}, "flip": {"enabled": True, "fields": ["bio"]}},
        )
        clear_registry()

        with _batch_ctx(source="test:flip-untracked"):
            entity = create_entity("character", name="Gandalf")
            char = Character.objects.create(entity=entity, bio="A wizard", title="Grey")

        char.refresh_from_db()
        assert "title" not in char.flip_map
        assert "bio" in char.flip_map
