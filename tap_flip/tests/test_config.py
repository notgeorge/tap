"""Tests for FLIP configuration system."""

import pytest

from tap_flip.config import (
    DEFAULT_FLIP_CONFIG,
    clear_registry,
    get_model_flip_config,
    is_batch_enabled,
    is_history_enabled,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Clear the FLIP registry before each test."""
    clear_registry()
    yield
    clear_registry()


class TestDefaultFlipConfig:
    """Tests for the default FLIP_CONFIG structure."""

    def test_default_config_has_all_sections(self):
        """Default config has history, batch, and consensus sections."""
        assert "history" in DEFAULT_FLIP_CONFIG
        assert "batch" in DEFAULT_FLIP_CONFIG
        assert "consensus" in DEFAULT_FLIP_CONFIG

    def test_all_sections_have_enabled_key(self):
        """Every section has an 'enabled' key."""
        for section in ["history", "batch", "consensus"]:
            assert "enabled" in DEFAULT_FLIP_CONFIG[section]

    def test_all_features_disabled_by_default(self):
        """All FLIP features are disabled by default (opt-in)."""
        assert DEFAULT_FLIP_CONFIG["history"]["enabled"] is False
        assert DEFAULT_FLIP_CONFIG["batch"]["enabled"] is False
        assert DEFAULT_FLIP_CONFIG["consensus"]["enabled"] is False

    def test_history_has_depth_settings(self):
        """History section has depth configuration."""
        assert "depth_revisions" in DEFAULT_FLIP_CONFIG["history"]
        assert "depth_days" in DEFAULT_FLIP_CONFIG["history"]


class TestGetModelFlipConfig:
    """Tests for get_model_flip_config function."""

    def test_model_without_flip_config_gets_defaults(self):
        """Model with no FLIP_CONFIG attribute uses defaults."""

        class NoConfigModel:
            pass

        config = get_model_flip_config(NoConfigModel)
        assert config["history"]["enabled"] is False
        assert config["batch"]["enabled"] is False

    def test_model_with_partial_override(self):
        """Model can override specific sections while inheriting others."""

        class PartialConfigModel:
            FLIP_CONFIG = {"history": {"enabled": True}}

        config = get_model_flip_config(PartialConfigModel)
        assert config["history"]["enabled"] is True
        # Batch and consensus inherit defaults
        assert config["batch"]["enabled"] is False
        assert config["consensus"]["enabled"] is False

    def test_model_with_nested_partial_override(self):
        """Model can override nested values within a section."""

        class NestedConfigModel:
            FLIP_CONFIG = {"history": {"enabled": True, "depth_revisions": 100}}

        config = get_model_flip_config(NestedConfigModel)
        assert config["history"]["enabled"] is True
        assert config["history"]["depth_revisions"] == 100
        # depth_days inherits default
        assert config["history"]["depth_days"] is None

    def test_config_cached_in_registry(self):
        """get_model_flip_config caches results."""

        class CachedModel:
            FLIP_CONFIG = {"history": {"enabled": True}}

        config1 = get_model_flip_config(CachedModel)
        config2 = get_model_flip_config(CachedModel)
        # Same object returned from cache
        assert config1 is config2

    def test_different_models_have_separate_configs(self):
        """Each model class has its own cached config."""

        class ModelA:
            FLIP_CONFIG = {"history": {"enabled": True}}

        class ModelB:
            FLIP_CONFIG = {"history": {"enabled": False}}

        config_a = get_model_flip_config(ModelA)
        config_b = get_model_flip_config(ModelB)

        assert config_a["history"]["enabled"] is True
        assert config_b["history"]["enabled"] is False


class TestIsHistoryEnabled:
    """Tests for is_history_enabled helper."""

    def test_history_enabled_when_configured(self):
        """is_history_enabled returns True for enabled models."""

        class HistoryModel:
            FLIP_CONFIG = {"history": {"enabled": True}}

        assert is_history_enabled(HistoryModel) is True

    def test_history_disabled_by_default(self):
        """is_history_enabled returns False for unconfigured models."""

        class DefaultModel:
            pass

        assert is_history_enabled(DefaultModel) is False

    def test_history_explicitly_disabled(self):
        """is_history_enabled respects explicit False."""

        class DisabledModel:
            FLIP_CONFIG = {"history": {"enabled": False}}

        assert is_history_enabled(DisabledModel) is False


class TestIsBatchEnabled:
    """Tests for is_batch_enabled helper."""

    def test_batch_disabled_by_default(self):
        """Batch is disabled by default (Phase 2 feature)."""

        class DefaultModel:
            pass

        assert is_batch_enabled(DefaultModel) is False

    def test_batch_enabled_when_configured(self):
        """is_batch_enabled returns True when configured."""

        class BatchModel:
            FLIP_CONFIG = {"batch": {"enabled": True}}

        assert is_batch_enabled(BatchModel) is True
