"""Lord of the Rings plugin — Middle-earth entities for constraint testing."""

from typing import Any

from tap_plugins.base import TapPluginConfig


class LotrConfig(TapPluginConfig):
    name = "plugins.lotr"
    verbose_name = "Lord of the Rings"
    label = "lotr"

    entity_types = [
        {
            "slug": "character",
            "name": "Character",
            "icon": "character",
            "description": "A being in Middle-earth.",
        },
        {
            "slug": "location",
            "name": "Location",
            "icon": "location",
            "description": "A place in Middle-earth.",
        },
        {
            "slug": "artifact",
            "name": "Artifact",
            "icon": "artifact",
            "description": "A significant object of power.",
        },
        {
            "slug": "race",
            "name": "Race",
            "icon": "race",
            "description": "A race of beings.",
        },
        {
            "slug": "faction",
            "name": "Faction",
            "description": "A group or alliance.",
        },
        {
            "slug": "sentinel",
            "name": "Sentinel",
            "description": "A watcher (wildcard test).",
        },
        {
            "slug": "citadel",
            "name": "Citadel",
            "description": "A fortified place (inbound block test).",
        },
        {
            "slug": "wanderer",
            "name": "Wanderer",
            "description": "An unconstrained traveler.",
        },
    ]

    edge_types = [
        {
            "slug": "WIELDS",
            "name": "Wields",
            "description": "Character wields an artifact.",
            # Edge constraint: character -> artifact
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
            # Edge constraint: character -> location
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
            # Edge constraint: artifact -> location
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
        # New edge type with constraint - demonstrates plugin extensibility
        # Character can MENTORS character even though Character's OUTBOUND_EDGES
        # doesn't list it (edge constraint grants permission)
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
