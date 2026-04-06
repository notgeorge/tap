"""TapPluginConfig — base class for TAP plugins.

Plugins subclass this and provide a tap-plugin.toml manifest at their root.
The manifest declares TAP-managed model types and bundled GRIFT files.

Edge types are still declared as a Python class attribute (edge manifest
declarations are deferred to a later spec version).

Override get_api_router() to expose API endpoints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def register_edge_types_from_list(edge_types: list[dict[str, Any]]) -> None:
    """Register edge constraints, property schemas, and default dimensions.

    Processes a list of edge type dicts in the same format used by
    TapPluginConfig.edge_types. Call this from any AppConfig.ready() that
    needs to register web or core edge types without subclassing TapPluginConfig.
    """
    from tap_grid.constraints import (
        register_edge_default_dimensions,
        register_edge_property_schema,
        register_edge_type_constraints,
    )

    for et in edge_types:
        slug = et["slug"]
        sources = et.get("sources")
        targets = et.get("targets")

        if sources is not None or targets is not None:
            register_edge_type_constraints(slug, sources, targets)

        if "property_schema" in et:
            register_edge_property_schema(slug, et["property_schema"])

        if "default_dimensions" in et:
            register_edge_default_dimensions(slug, et["default_dimensions"])


class TapPluginConfig(AppConfig):
    """Base AppConfig for TAP plugins.

    Subclass this and provide a tap-plugin.toml manifest at the plugin root.
    Declare edge types as a class attribute (edge manifest support is deferred)::

        class MyPluginConfig(TapPluginConfig):
            name = "my_plugin"
            verbose_name = "My Plugin"

            edge_types = [
                {
                    "slug": "APPLIES_TO",
                    "name": "Applies To",
                    "description": "Concept applies to precept",
                    "sources": [{"type": "concept"}],
                    "targets": [{"type": "precept"}],
                },
            ]

    Edge constraints in edge_types:
        - sources: list of {"type": "..."} dicts for allowed source node types
        - targets: list of {"type": "..."} dicts for allowed target node types
        - Omit sources/targets for wildcard (any node type allowed)

    Entity type metadata (name, description, icon) is read from class attributes
    on each declared model class:
        - ENTITY_NAME (str, optional): human-readable name; falls back to slug
        - ENTITY_DESCRIPTION (str, optional): short description; falls back to ""
        - ENTITY_ICON (str, optional): icon key; falls back to ""
    """

    # Edge types remain a Python class attribute (manifest support deferred).
    edge_types: list[dict[str, Any]] = []

    # Resolved at ready() time; None until then.
    _manifest: Any = None  # PluginManifest | None

    @property
    def manifest(self) -> Any:
        """Return the loaded PluginManifest, or None if not yet loaded."""
        return self._manifest

    def ready(self) -> None:
        self._load_and_validate_manifest()
        self._register_edge_constraints()
        self._register_types_from_manifest()

    def get_api_router(self) -> Any:
        """Return a ninja.Router for this plugin, or None.

        Override to expose endpoints at /api/v1/plugins/<label>/...
        tap_api discovers and mounts these automatically.
        """
        return None

    # ---------------------------------------------------------------------------
    # Manifest loading
    # ---------------------------------------------------------------------------

    def _plugin_root(self) -> Path:
        """Return the filesystem root of this plugin package."""
        import importlib

        mod = importlib.import_module(self.name)
        return Path(mod.__file__).parent  # type: ignore[arg-type]

    def _load_and_validate_manifest(self) -> None:
        """Load tap-plugin.toml and run structural + path validation."""
        from tap_plugins.manifest import (
            PluginManifestError,
            load_manifest,
            validate_model_classes,
            warn_undeclared_convention_files,
        )

        root = self._plugin_root()
        try:
            manifest = load_manifest(root)
        except PluginManifestError as exc:
            raise RuntimeError(f"Plugin '{self.name}' failed manifest validation: {exc}") from exc

        try:
            validate_model_classes(manifest)
        except PluginManifestError as exc:
            raise RuntimeError(f"Plugin '{self.name}' manifest model class validation failed: {exc}") from exc

        warn_undeclared_convention_files(manifest)
        self._manifest = manifest

    # ---------------------------------------------------------------------------
    # Type registration
    # ---------------------------------------------------------------------------

    def _register_edge_constraints(self) -> None:
        """Register edge constraints and property schemas from edge_types."""
        register_edge_types_from_list(self.edge_types)

    def _register_types_from_manifest(self) -> None:
        """Register entity and edge types into the EntityType table from manifest.

        Entity types are driven by [[models]] entries in tap-plugin.toml.
        Display metadata is read from ENTITY_NAME, ENTITY_DESCRIPTION, ENTITY_ICON
        class attributes on each declared model class.

        Edge types are driven by the edge_types class attribute (manifest support deferred).
        """
        if self._manifest is None:
            return

        try:
            from django.utils.module_loading import import_string

            from tap_grid.models import EntityType

            for model_entry in self._manifest.models:
                cls = import_string(model_entry.class_path)
                EntityType.objects.update_or_create(
                    slug=model_entry.slug,
                    defaults={
                        "name": getattr(cls, "ENTITY_NAME", model_entry.slug),
                        "icon": getattr(cls, "ENTITY_ICON", ""),
                        "description": getattr(cls, "ENTITY_DESCRIPTION", ""),
                        "plugin_name": self.name,
                    },
                )

            for et in self.edge_types:
                EntityType.objects.update_or_create(
                    slug=et["slug"],
                    defaults={
                        "name": et.get("name", et["slug"]),
                        "icon": et.get("icon", ""),
                        "description": et.get("description", ""),
                        "plugin_name": self.name,
                    },
                )

        except (OperationalError, ProgrammingError):
            logger.debug("EntityType table not ready; skipping type registration.")
