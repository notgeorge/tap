"""Tests for Registry and ScopedRegistry metadata fields (title, description, creator)."""

import pytest

from tap_grid.registry import Registry, ScopedRegistry, meta_registry, search_runner_registry


@pytest.fixture()
def clean_meta():
    """Save and restore meta_registry state so test-created registries don't pollute it."""
    saved = meta_registry.all()
    yield
    meta_registry._reset_for_testing(saved)


class TestRegistryMetadata:
    """title, description, and creator fields on Registry."""

    def test_title_defaults_to_formatted_name(self):
        r: Registry[str] = Registry("my_test_registry_default", _skip_meta=True)
        assert r.title == "My Test Registry Default"

    def test_title_explicit(self):
        r: Registry[str] = Registry("x_title", title="Custom Label", _skip_meta=True)
        assert r.title == "Custom Label"

    def test_description_defaults_to_empty(self):
        r: Registry[str] = Registry("x_desc", _skip_meta=True)
        assert r.description == ""

    def test_description_explicit(self):
        r: Registry[str] = Registry("x_desc_exp", description="Stores widgets.", _skip_meta=True)
        assert r.description == "Stores widgets."

    def test_creator_auto_inferred(self):
        r: Registry[str] = Registry("x_creator_auto", _skip_meta=True)
        assert r.creator == "tap_grid.tests.test_registry"

    def test_creator_explicit(self):
        r: Registry[str] = Registry("x_creator_exp", creator="tap_plugins.custom", _skip_meta=True)
        assert r.creator == "tap_plugins.custom"


class TestScopedRegistryMetadata:
    """title, description, and creator fields on ScopedRegistry."""

    def test_title_defaults_to_formatted_name(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_title_default")
        assert r.title == "Scoped Meta Title Default"

    def test_title_explicit(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_title_exp", title="My Scoped Registry")
        assert r.title == "My Scoped Registry"

    def test_description_defaults_to_empty(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_desc_default")
        assert r.description == ""

    def test_description_explicit(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_desc_exp", description="Scoped runners.")
        assert r.description == "Scoped runners."

    def test_creator_auto_inferred(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_creator_auto")
        assert r.creator == "tap_grid.tests.test_registry"

    def test_creator_explicit(self, clean_meta):
        r: ScopedRegistry[str] = ScopedRegistry("scoped_meta_creator_exp", creator="tap_ai.module")
        assert r.creator == "tap_ai.module"


class TestModuleLevelRegistryMetadata:
    """Verify that module-level registries carry the expected metadata."""

    def test_search_runner_registry_title(self):
        assert search_runner_registry.title == "Search Runner Registry"

    def test_search_runner_registry_description(self):
        assert "search runner" in search_runner_registry.description.lower()

    def test_search_runner_registry_creator(self):
        assert search_runner_registry.creator == "tap_grid.registry"

    def test_meta_registry_metadata(self):
        assert meta_registry.title == "Meta Registry"
        assert meta_registry.creator == "tap_grid.registry"
