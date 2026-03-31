"""Tests for FLIP configuration system."""

import pytest

from tap_grid.flip import (
    DEFAULT_FLIP_CONFIG,
    clear_registry,
    get_flip_fields,
    get_model_flip_config,
    is_batch_enabled,
    is_flip_enabled,
)
from tap_grid.history import is_history_enabled


@pytest.fixture(autouse=True)
def reset_registry():
    """Clear the FLIP registry before each test."""
    clear_registry()
    yield
    clear_registry()


class TestDefaultFlipConfig:
    """Tests for the default FLIP_CONFIG structure."""

    def test_default_config_has_batch_and_flip_sections(self):
        """Default config has batch and flip sections only (history is independent)."""
        assert "batch" in DEFAULT_FLIP_CONFIG
        assert "flip" in DEFAULT_FLIP_CONFIG
        assert "history" not in DEFAULT_FLIP_CONFIG
        assert "consensus" not in DEFAULT_FLIP_CONFIG

    def test_all_sections_have_enabled_key(self):
        """Every section has an 'enabled' key."""
        for section in ["batch", "flip"]:
            assert "enabled" in DEFAULT_FLIP_CONFIG[section]

    def test_all_features_disabled_by_default(self):
        """All FLIP features are disabled by default (opt-in)."""
        assert DEFAULT_FLIP_CONFIG["batch"]["enabled"] is False
        assert DEFAULT_FLIP_CONFIG["flip"]["enabled"] is False

    def test_flip_has_fields_list(self):
        """Flip section has an explicit fields allow-list."""
        assert "fields" in DEFAULT_FLIP_CONFIG["flip"]
        assert DEFAULT_FLIP_CONFIG["flip"]["fields"] == []


class TestGetModelFlipConfig:
    """Tests for get_model_flip_config function."""

    def test_model_without_flip_config_gets_defaults(self):
        """Model with no FLIP_CONFIG attribute uses defaults."""

        class NoConfigModel:
            pass

        config = get_model_flip_config(NoConfigModel)
        assert config["batch"]["enabled"] is False
        assert config["flip"]["enabled"] is False

    def test_model_with_partial_batch_override(self):
        """Model can enable batch while flip inherits defaults."""

        class BatchOnlyModel:
            FLIP_CONFIG = {"batch": {"enabled": True}}

        config = get_model_flip_config(BatchOnlyModel)
        assert config["batch"]["enabled"] is True
        assert config["flip"]["enabled"] is False

    def test_model_with_flip_fields(self):
        """Model can declare specific fields for FLIP tracking."""

        class FlipModel:
            FLIP_CONFIG = {"flip": {"enabled": True, "fields": ["ip_address", "status"]}}

        config = get_model_flip_config(FlipModel)
        assert config["flip"]["enabled"] is True
        assert config["flip"]["fields"] == ["ip_address", "status"]

    def test_config_cached_in_registry(self):
        """get_model_flip_config caches results."""

        class CachedModel:
            FLIP_CONFIG = {"batch": {"enabled": True}}

        config1 = get_model_flip_config(CachedModel)
        config2 = get_model_flip_config(CachedModel)
        assert config1 is config2

    def test_different_models_have_separate_configs(self):
        """Each model class has its own cached config."""

        class ModelA:
            FLIP_CONFIG = {"batch": {"enabled": True}}

        class ModelB:
            FLIP_CONFIG = {"batch": {"enabled": False}}

        assert get_model_flip_config(ModelA)["batch"]["enabled"] is True
        assert get_model_flip_config(ModelB)["batch"]["enabled"] is False


class TestIsHistoryEnabled:
    """Tests for is_history_enabled helper.

    History enablement is determined by whether the model has a HistoricalRecords
    manager attached, not by FLIP_CONFIG.
    """

    def test_history_enabled_when_manager_present(self):
        """is_history_enabled returns True when model has a history manager."""

        class WithHistoryModel:
            history = object()  # simulates HistoricalRecords manager

        assert is_history_enabled(WithHistoryModel) is True

    def test_history_disabled_when_no_manager(self):
        """is_history_enabled returns False when model has no history manager."""

        class NoHistoryModel:
            pass

        assert is_history_enabled(NoHistoryModel) is False


class TestIsBatchEnabled:
    """Tests for is_batch_enabled helper."""

    def test_batch_disabled_by_default(self):
        """Batch is disabled by default."""

        class DefaultModel:
            pass

        assert is_batch_enabled(DefaultModel) is False

    def test_batch_enabled_when_configured(self):
        """is_batch_enabled returns True when configured."""

        class BatchModel:
            FLIP_CONFIG = {"batch": {"enabled": True}}

        assert is_batch_enabled(BatchModel) is True


class TestIsFlipEnabled:
    """Tests for is_flip_enabled helper."""

    def test_flip_disabled_by_default(self):
        """FLIP is disabled by default."""

        class DefaultModel:
            pass

        assert is_flip_enabled(DefaultModel) is False

    def test_flip_enabled_when_configured(self):
        """is_flip_enabled returns True when configured."""

        class FlipModel:
            FLIP_CONFIG = {"flip": {"enabled": True, "fields": ["name"]}}

        assert is_flip_enabled(FlipModel) is True


class TestGetFlipFields:
    """Tests for get_flip_fields helper."""

    def test_empty_fields_by_default(self):
        """No fields tracked by default."""

        class DefaultModel:
            pass

        assert get_flip_fields(DefaultModel) == []

    def test_returns_configured_fields(self):
        """Returns the explicit allow-list from FLIP_CONFIG."""

        class TrackedModel:
            FLIP_CONFIG = {"flip": {"enabled": True, "fields": ["ip_address", "status"]}}

        assert get_flip_fields(TrackedModel) == ["ip_address", "status"]
