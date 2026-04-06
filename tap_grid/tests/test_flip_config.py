"""Tests for FLIP default-on behavior (tap_grid.flip)."""


from tap_grid.flip import is_flip_enabled, update_flip_map
from tap_grid.history import is_history_enabled


class TestIsFlipEnabled:
    """is_flip_enabled is True for models with service-writeable fields."""

    def test_returns_true_for_model_with_service_schemas(self):
        """Model with SERVICE_SCHEMAS properties is FLIP-enabled."""

        class NodeModel:
            SERVICE_SCHEMAS = {
                "create": {"type": "object", "properties": {"name": {"type": "string"}}},
                "patch": {"type": "object", "properties": {"name": {"type": "string"}}},
                "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
            }

        assert is_flip_enabled(NodeModel) is True

    def test_returns_false_for_model_without_service_schemas(self):
        """Model with no SERVICE_SCHEMAS is not FLIP-enabled."""

        class NoSchemaModel:
            pass

        assert is_flip_enabled(NoSchemaModel) is False

    def test_returns_false_for_model_with_empty_service_schemas(self):
        """Model with SERVICE_SCHEMAS but no properties is not FLIP-enabled."""

        class EmptyModel:
            SERVICE_SCHEMAS = {
                "create": {"type": "object"},
                "patch": {"type": "object"},
                "replace": {"type": "object"},
            }

        assert is_flip_enabled(EmptyModel) is False

    def test_returns_false_for_internal_only_model(self):
        """Internal-only model types are excluded from FLIP."""

        class InternalModel:
            INTERNAL_ONLY = True
            SERVICE_SCHEMAS = {
                "create": {"type": "object", "properties": {"name": {"type": "string"}}},
                "patch": {"type": "object", "properties": {}},
                "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
            }

        assert is_flip_enabled(InternalModel) is False

    def test_returns_true_if_any_schema_has_properties(self):
        """FLIP is enabled if at least one schema key has properties."""

        class PatchOnlyFields:
            SERVICE_SCHEMAS = {
                "create": {"type": "object"},
                "patch": {"type": "object", "properties": {"status": {"type": "string"}}},
                "replace": {"type": "object"},
            }

        assert is_flip_enabled(PatchOnlyFields) is True


class TestIsHistoryEnabled:
    """History enablement is determined by the presence of a HistoricalRecords manager."""

    def test_history_enabled_when_manager_present(self):
        class WithHistoryModel:
            history = object()

        assert is_history_enabled(WithHistoryModel) is True

    def test_history_disabled_when_no_manager(self):
        class NoHistoryModel:
            pass

        assert is_history_enabled(NoHistoryModel) is False


class TestUpdateFlipMapDefaultOn:
    """update_flip_map derives tracked fields from SERVICE_SCHEMAS by default."""

    def _make(self, schemas=None, internal_only=False):
        cls = type("TestModel", (), {
            "SERVICE_SCHEMAS": schemas or {},
            "INTERNAL_ONLY": internal_only,
        })
        instance = object.__new__(cls)
        instance.flip_map = {}
        return instance

    def test_stamps_service_writeable_fields_on_full_save(self):
        instance = self._make({
            "create": {"type": "object", "properties": {"name": {"type": "string"}}},
            "patch": {"type": "object", "properties": {"name": {"type": "string"}}},
            "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
        })
        result = update_flip_map(instance, None, "batch-abc")
        assert result is True
        assert instance.flip_map == {"name": "batch-abc"}

    def test_stamps_only_changed_fields_on_partial_save(self):
        instance = self._make({
            "create": {"type": "object", "properties": {"name": {"type": "string"}, "bio": {"type": "string"}}},
            "patch": {"type": "object", "properties": {"name": {"type": "string"}, "bio": {"type": "string"}}},
            "replace": {"type": "object", "properties": {"name": {"type": "string"}, "bio": {"type": "string"}}},
        })
        result = update_flip_map(instance, ["name"], "batch-123")
        assert result is True
        assert instance.flip_map == {"name": "batch-123"}
        assert "bio" not in instance.flip_map

    def test_returns_false_with_no_batch_id(self):
        instance = self._make({
            "create": {"type": "object", "properties": {"name": {"type": "string"}}},
            "patch": {"type": "object", "properties": {"name": {"type": "string"}}},
            "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
        })
        result = update_flip_map(instance, None, None)
        assert result is False
        assert instance.flip_map == {}

    def test_returns_false_for_internal_only_model(self):
        instance = self._make(
            {
                "create": {"type": "object", "properties": {"name": {"type": "string"}}},
                "patch": {"type": "object", "properties": {"name": {"type": "string"}}},
                "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
            internal_only=True,
        )
        result = update_flip_map(instance, None, "batch-abc")
        assert result is False
        assert instance.flip_map == {}

    def test_returns_false_when_no_service_schemas(self):
        instance = self._make({})
        result = update_flip_map(instance, None, "batch-abc")
        assert result is False

    def test_union_of_all_schema_properties(self):
        """Fields from create, patch, and replace are all tracked."""
        instance = self._make({
            "create": {"type": "object", "properties": {"title": {"type": "string"}}},
            "patch": {"type": "object", "properties": {"description": {"type": "string"}}},
            "replace": {"type": "object", "properties": {"title": {"type": "string"}, "source": {"type": "string"}}},
        })
        result = update_flip_map(instance, None, "batch-xyz")
        assert result is True
        assert set(instance.flip_map.keys()) == {"title", "description", "source"}

    def test_overwrites_previous_batch_id(self):
        instance = self._make({
            "create": {"type": "object", "properties": {"name": {"type": "string"}}},
            "patch": {"type": "object", "properties": {"name": {"type": "string"}}},
            "replace": {"type": "object", "properties": {"name": {"type": "string"}}},
        })
        instance.flip_map = {"name": "old-batch"}
        update_flip_map(instance, ["name"], "new-batch")
        assert instance.flip_map["name"] == "new-batch"
