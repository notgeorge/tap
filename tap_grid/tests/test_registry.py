"""Tests for Registry and ScopedRegistry metadata and validator hooks."""

import re

import pytest
from django.core.exceptions import ImproperlyConfigured

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


class TestScopedRegistryValidators:
    """Optional validate_key / validate_scope callbacks (req-grid-registry-scope-validators)."""

    _FORMAT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

    @classmethod
    def _validate(cls, value: str) -> None:
        if not cls._FORMAT.fullmatch(value):
            raise ImproperlyConfigured(f"Invalid registry token: {value!r}")

    def _runner(self, module: str = "ok.scope"):
        def runner():
            return None

        runner.__module__ = module
        return runner

    def test_defaults_are_no_op(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry("vk_default")
        runner = self._runner()
        # No validators → any non-empty key registers and looks up fine.
        r.register("anything!*goes", runner)
        assert r.get("ok.scope:anything!*goes") is runner

    def test_register_validates_key(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry("vk_reg_key", validate_key=self._validate)
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.register("bad key", self._runner(), scope="ok.scope")

    def test_register_validates_scope(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry("vk_reg_scope", validate_scope=self._validate)
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.register("ok", self._runner(), scope="bad scope")

    def test_register_validates_inferred_scope(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry("vk_reg_inferred", validate_scope=self._validate)
        runner = self._runner(module="bad scope from module")
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.register("ok", runner)

    def test_failed_register_leaves_state_unchanged(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry(
            "vk_reg_atomic",
            validate_key=self._validate,
            validate_scope=self._validate,
        )
        with pytest.raises(ImproperlyConfigured):
            r.register("bad key", self._runner(), scope="ok.scope")
        # Scope dict should NOT have been created for the rejected registration.
        assert "ok.scope" not in r.all()
        assert r.keys() == []

    def test_get_validates_fully_qualified(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry(
            "vk_get_fq",
            validate_key=self._validate,
            validate_scope=self._validate,
        )
        r.register("ok", self._runner(), scope="ok.scope")
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.get("bad scope:ok")
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.get("ok.scope:bad key")

    def test_get_validates_with_scope_kwarg(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry(
            "vk_get_kwarg",
            validate_key=self._validate,
            validate_scope=self._validate,
        )
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.get("ok", scope="bad scope")

    def test_get_short_key_validates_key_only(self, clean_meta):
        r: ScopedRegistry = ScopedRegistry("vk_get_short", validate_key=self._validate)
        runner = self._runner()
        r.register("ok", runner, scope="only.scope")
        # Valid short key resolves.
        assert r.get("ok") is runner
        # Invalid short key fails validation before lookup.
        with pytest.raises(ImproperlyConfigured, match="Invalid registry token"):
            r.get("bad key")

    def test_validator_exception_propagates_unchanged(self, clean_meta):
        class MyDomainError(Exception):
            pass

        def strict(value: str) -> None:
            raise MyDomainError(f"nope: {value}")

        r: ScopedRegistry = ScopedRegistry("vk_propagate", validate_key=strict)
        with pytest.raises(MyDomainError, match="nope: anything"):
            r.register("anything", self._runner(), scope="ok.scope")

    def test_iteration_helpers_do_not_revalidate(self, clean_meta):
        # Validators added after-the-fact would still let stored data be enumerated.
        # Simulate by registering with a permissive registry then swapping in a strict
        # validator — keys(), all(), scopes(), get_all() should not run validators.
        r: ScopedRegistry = ScopedRegistry("vk_iter")
        r.register("legacy key", self._runner(), scope="ok.scope")
        # Now attach a strict validator manually (mirrors hypothetical reconfigure).
        r._validate_key = self._validate  # type: ignore[attr-defined]
        r._validate_scope = self._validate  # type: ignore[attr-defined]
        # Iteration paths should not raise — they expose stored entries as-is.
        assert r.keys() == ["ok.scope:legacy key"]
        assert r.scopes() == ["ok.scope"]
        legacy = r.get_all("legacy key")
        assert "ok.scope" in legacy
        assert r.all() == {"ok.scope": {"legacy key": legacy["ok.scope"]}}


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
