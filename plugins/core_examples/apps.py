"""Core examples plugin — abstract philosophical entities for demos and testing."""

from typing import Any

from tap_plugins.base import TapPluginConfig


class CoreExamplesConfig(TapPluginConfig):
    name = "plugins.core_examples"
    verbose_name = "Core Examples"
    label = "core_examples"

    entity_types = [
        {
            "slug": "concept",
            "name": "Concept",
            "description": "An abstract idea or principle.",
        },
        {
            "slug": "precept",
            "name": "Precept",
            "description": "A rule or instruction derived from a concept.",
        },
    ]

    edge_types = [
        {
            "slug": "APPLIES_TO",
            "name": "Applies To",
            "description": "A concept gives rise to a precept.",
        },
        {
            "slug": "DEPENDS_ON",
            "name": "Depends On",
            "description": "General dependency between any entities.",
        },
    ]

    def ready(self) -> None:
        super().ready()
        from tap_grid.registry import register_search_runner
        from plugins.core_examples.searches import list_concepts

        register_search_runner("list-concepts", list_concepts)

    def get_api_router(self) -> Any:
        from plugins.core_examples.api import router

        return router
