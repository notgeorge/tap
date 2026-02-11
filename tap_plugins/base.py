"""
TapPluginConfig — base class for TAP plugins.

Plugins subclass this instead of Django's AppConfig. Declare entity_types
and edge_types as class attributes; they're auto-registered on startup.
Override get_api_router() to expose API endpoints.
"""

import logging
from typing import Any

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


class TapPluginConfig(AppConfig):
    """Base AppConfig for TAP plugins.

    Subclass this and declare your types::

        class MyPluginConfig(TapPluginConfig):
            name = "my_plugin"
            verbose_name = "My Plugin"

            entity_types = [
                {"slug": "concept", "display_name": "Concept", "icon": "", "description": "An abstract idea"},
            ]
            edge_types = [
                {
                    "slug": "applies_to",
                    "display_name": "Applies To",
                    "description": "Concept applies to precept",
                    # Optional: edge constraints (omit for unconstrained)
                    "sources": [{"type": "concept"}],
                    "targets": [{"type": "precept"}],
                },
            ]

    Edge constraints in edge_types:
        - sources: list of {"type": "..."} dicts for allowed source node types
        - targets: list of {"type": "..."} dicts for allowed target node types
        - Omit sources/targets for wildcard (any node type allowed)
    """

    # Override in subclasses
    entity_types: list[dict[str, Any]] = []
    edge_types: list[dict[str, Any]] = []

    def ready(self) -> None:
        self._register_types()

    def get_api_router(self) -> Any:
        """Return a ninja.Router for this plugin, or None.

        Override to expose endpoints at /api/v1/plugins/<label>/...
        tap_api discovers and mounts these automatically.
        """
        return None

    def _register_types(self) -> None:
        """Register entity and edge types into the EntityType table.

        Also registers edge constraints from sources/targets in edge_types.

        Uses get_or_create for idempotency — safe to call on every startup.
        Catches DB errors gracefully for migrate/makemigrations commands
        where the table may not exist yet.
        """
        # Register edge constraints (always, even if DB not ready)
        self._register_edge_constraints()

        try:
            from tap_core.models import EntityType

            for et in self.entity_types:
                EntityType.objects.get_or_create(
                    slug=et["slug"],
                    defaults={
                        "display_name": et.get("display_name", et["slug"]),
                        "icon": et.get("icon", ""),
                        "description": et.get("description", ""),
                        "plugin_name": self.name,
                    },
                )
            for et in self.edge_types:
                EntityType.objects.get_or_create(
                    slug=et["slug"],
                    defaults={
                        "display_name": et.get("display_name", et["slug"]),
                        "icon": et.get("icon", ""),
                        "description": et.get("description", ""),
                        "plugin_name": self.name,
                    },
                )
        except OperationalError, ProgrammingError:
            # Table doesn't exist yet (running migrations for the first time)
            logger.debug("EntityType table not ready; skipping type registration.")

    def _register_edge_constraints(self) -> None:
        """Register edge constraints from edge_types into the constraint registry.

        Called before DB registration so constraints are available even during
        migrations.
        """
        from tap_core.constraints import register_edge_type_constraints

        for et in self.edge_types:
            slug = et["slug"]
            sources = et.get("sources")  # None if not specified (wildcard)
            targets = et.get("targets")  # None if not specified (wildcard)

            # Only register if at least one constraint is specified
            if sources is not None or targets is not None:
                register_edge_type_constraints(slug, sources, targets)
