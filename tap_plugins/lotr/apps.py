"""Lord of the Rings plugin — Middle-earth entities for constraint testing."""

from tap_plugins.base import TapPluginConfig


class LotrConfig(TapPluginConfig):
    name = "tap_plugins.lotr"
    verbose_name = "Lord of the Rings"
    label = "lotr"

    entity_types = [
        {
            "slug": "character",
            "display_name": "Character",
            "description": "A being in Middle-earth.",
        },
        {
            "slug": "location",
            "display_name": "Location",
            "description": "A place in Middle-earth.",
        },
        {
            "slug": "artifact",
            "display_name": "Artifact",
            "description": "A significant object of power.",
        },
        {
            "slug": "race",
            "display_name": "Race",
            "description": "A race of beings.",
        },
        {
            "slug": "faction",
            "display_name": "Faction",
            "description": "A group or alliance.",
        },
        {
            "slug": "sentinel",
            "display_name": "Sentinel",
            "description": "A watcher (wildcard test).",
        },
        {
            "slug": "citadel",
            "display_name": "Citadel",
            "description": "A fortified place (inbound block test).",
        },
        {
            "slug": "wanderer",
            "display_name": "Wanderer",
            "description": "An unconstrained traveler.",
        },
    ]

    edge_types = [
        {
            "slug": "WIELDS",
            "display_name": "Wields",
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
            "display_name": "Located In",
            "description": "Entity is located in a place.",
            # Edge constraint: character -> location
            "sources": [{"type": "character"}],
            "targets": [{"type": "location"}],
        },
        {
            "slug": "RULES",
            "display_name": "Rules",
            "description": "Character rules a location.",
        },
        {
            "slug": "BELONGS_TO",
            "display_name": "Belongs To",
            "description": "Character belongs to a race.",
        },
        {
            "slug": "MEMBER_OF",
            "display_name": "Member Of",
            "description": "Character is member of a faction.",
        },
        {
            "slug": "ALLIES_WITH",
            "display_name": "Allies With",
            "description": "Entities are allied.",
        },
        {
            "slug": "ENEMIES_WITH",
            "display_name": "Enemies With",
            "description": "Entities are enemies.",
        },
        {
            "slug": "FORGED_IN",
            "display_name": "Forged In",
            "description": "Artifact was forged in a location.",
            # Edge constraint: artifact -> location
            "sources": [{"type": "artifact"}],
            "targets": [{"type": "location"}],
        },
        {
            "slug": "CONTAINS",
            "display_name": "Contains",
            "description": "Location contains another location.",
        },
        {
            "slug": "REFERENCES",
            "display_name": "References",
            "description": "Sentinel references anything (wildcard).",
        },
        {
            "slug": "PROTECTS",
            "display_name": "Protects",
            "description": "Citadel protects a location.",
        },
        # New edge type with constraint - demonstrates plugin extensibility
        # Character can MENTORS character even though Character's OUTBOUND_EDGES
        # doesn't list it (edge constraint grants permission)
        {
            "slug": "MENTORS",
            "display_name": "Mentors",
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
