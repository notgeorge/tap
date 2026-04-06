"""Lord of the Rings plugin — Middle-earth entities for constraint testing."""

from typing import Any

from tap_plugins.base import TapPluginConfig


class LotrConfig(TapPluginConfig):
    name = "plugins.lotr"
    verbose_name = "Lord of the Rings"
    label = "lotr"

    # Entity types are declared in tap-plugin.toml and loaded from model classes.
    # Display metadata (name, description, icon) comes from ENTITY_NAME /
    # ENTITY_DESCRIPTION / ENTITY_ICON class attributes on each model.

    # Edge type declarations remain here until manifest support for edges lands.
    edge_types = [
        {
            "slug": "WIELDS",
            "name": "Wields",
            "description": "Character wields an artifact.",
            "sources": [{"type": "character"}],
            "targets": [{"type": "artifact"}],
            "property_schema": {
                "type": "object",
                "properties": {
                    "proficiency": {
                        "type": "string",
                        "enum": ["novice", "apprentice", "master"],
                    },
                    "primary": {"type": "boolean"},
                },
            },
        },
        {
            "slug": "LOCATED_IN",
            "name": "Located In",
            "description": "Entity is located in a place.",
            "sources": [{"type": "character"}],
            "targets": [{"type": "location"}],
        },
        {
            "slug": "RULES",
            "name": "Rules",
            "description": "Character rules a location.",
        },
        {
            "slug": "BELONGS_TO",
            "name": "Belongs To",
            "description": "Character belongs to a race.",
        },
        {
            "slug": "MEMBER_OF",
            "name": "Member Of",
            "description": "Character is member of a faction.",
        },
        {
            "slug": "ALLIES_WITH",
            "name": "Allies With",
            "description": "Entities are allied.",
        },
        {
            "slug": "ENEMIES_WITH",
            "name": "Enemies With",
            "description": "Entities are enemies.",
        },
        {
            "slug": "FORGED_IN",
            "name": "Forged In",
            "description": "Artifact was forged in a location.",
            "sources": [{"type": "artifact"}],
            "targets": [{"type": "location"}],
        },
        {
            "slug": "CONTAINS",
            "name": "Contains",
            "description": "Location contains another location.",
        },
        {
            "slug": "REFERENCES",
            "name": "References",
            "description": "Sentinel references anything (wildcard).",
        },
        {
            "slug": "PROTECTS",
            "name": "Protects",
            "description": "Citadel protects a location.",
        },
        {
            "slug": "MENTORS",
            "name": "Mentors",
            "description": "One character mentors another.",
            "sources": [{"type": "character"}],
            "targets": [{"type": "character"}],
            "property_schema": {
                "type": "object",
                "required": ["discipline"],
                "properties": {
                    "discipline": {"type": "string"},
                    "duration_years": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        },
    ]

    def ready(self) -> None:
        super().ready()
        from plugins.lotr.forms import CharacterEditorDescriptor
        from plugins.lotr.searches import list_characters_with_bio
        from tap_grid.registry import register_search_runner
        from tap_web.registry import register_editor

        register_search_runner("list-characters-with-bio", list_characters_with_bio)
        register_editor(CharacterEditorDescriptor())

    def get_api_router(self) -> Any:
        from plugins.lotr.api import router

        return router
