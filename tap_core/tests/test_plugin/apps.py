"""Test plugin — abstract philosophical entities for proving the core model."""

from tap_plugins.base import TapPluginConfig


class TestPluginConfig(TapPluginConfig):
    name = "tap_core.tests.test_plugin"
    verbose_name = "Test Plugin"
    label = "test_plugin"

    entity_types = [
        {
            "slug": "concept",
            "display_name": "Concept",
            "description": "An abstract idea or principle.",
        },
        {
            "slug": "precept",
            "display_name": "Precept",
            "description": "A rule or instruction derived from a concept.",
        },
    ]

    edge_types = [
        {
            "slug": "applies_to",
            "display_name": "Applies To",
            "description": "A concept gives rise to a precept.",
        },
        {
            "slug": "depends_on",
            "display_name": "Depends On",
            "description": "General dependency between any entities.",
        },
    ]
