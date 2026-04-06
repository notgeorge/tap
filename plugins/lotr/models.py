"""Domain models for the Lord of the Rings plugin.

This plugin provides diverse constraint patterns for testing edge validation:
- Multiple target types per edge
- Self-referential edges (location -> location)
- Bidirectional edges (faction <-> faction)
- Wildcard edges (sentinel -> anything)
- Empty constraint lists (blocks all)
- No constraints (allows all)
"""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Character(BaseModel):
    """A being in Middle-earth (Frodo, Gandalf, Sauron, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "character"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "bio": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "bio"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "ellipse"}}

    # Characters can form many types of edges to various targets
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "artifact"}],
            "edges": [{"type": "WIELDS"}],
        },
        {
            "nodes": [{"type": "location"}],
            "edges": [{"type": "LOCATED_IN"}, {"type": "RULES"}],
        },
        {
            "nodes": [{"type": "race"}],
            "edges": [{"type": "BELONGS_TO"}],
        },
        {
            "nodes": [{"type": "faction"}],
            "edges": [{"type": "MEMBER_OF"}],
        },
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}],
        },
    ]

    # Characters can receive alliance/enemy edges from other characters
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    bio = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_character"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Location(BaseModel):
    """A place in Middle-earth (Shire, Mordor, Rivendell, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "location"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "description": {"type": "string"},
        "realm": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "description", "realm"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "round-rectangle"}}

    # Locations can contain other locations (Shire contains Bag End)
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "location"}],
            "edges": [{"type": "CONTAINS"}],
        },
    ]

    # Locations receive many types of edges
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "LOCATED_IN"}, {"type": "RULES"}],
        },
        {
            "nodes": [{"type": "artifact"}],
            "edges": [{"type": "FORGED_IN"}],
        },
        {
            "nodes": [{"type": "location"}],
            "edges": [{"type": "CONTAINS"}],
        },
        {
            "nodes": [{"type": "citadel"}],
            "edges": [{"type": "PROTECTS"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    realm = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_location"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Artifact(BaseModel):
    """A significant object (The One Ring, Sting, Andúril, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "artifact"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "power": {"type": "string"},
        "origin": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "power", "origin"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Artifacts can only be forged in locations
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "location"}],
            "edges": [{"type": "FORGED_IN"}],
        },
    ]

    # Artifacts can be wielded by characters
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "WIELDS"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    power = models.TextField(blank=True, default="")
    origin = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_artifact"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Race(BaseModel):
    """A race of beings (Hobbit, Elf, Dwarf, Human, Wizard, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "race"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "homeland": {"type": "string"},
        "traits": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "homeland", "traits"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Races cannot create any outbound edges (empty list = block all)
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = []

    # Races receive BELONGS_TO from characters
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "BELONGS_TO"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    homeland = models.CharField(max_length=255, blank=True, default="")
    traits = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_race"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Faction(BaseModel):
    """A group or alliance (Fellowship, Mordor, Rohan, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "faction"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "purpose": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "purpose"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Factions can ally or be enemies with other factions
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "faction"}],
            "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}],
        },
    ]

    # Factions receive membership and alliance edges
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "character"}],
            "edges": [{"type": "MEMBER_OF"}],
        },
        {
            "nodes": [{"type": "faction"}],
            "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    purpose = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_faction"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Sentinel(BaseModel):
    """A watcher that can reference anything (wildcard test case)."""

    ENTITY_TYPE: ClassVar[str] = "sentinel"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "watch_domain": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "watch_domain"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Sentinel uses wildcard: REFERENCES can point to ANY node type
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            # No "nodes" key = wildcard, can connect to any type
            "edges": [{"type": "REFERENCES"}],
        },
    ]

    # Sentinels can receive REFERENCES from other sentinels
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "sentinel"}],
            "edges": [{"type": "REFERENCES"}],
        },
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    watch_domain = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_sentinel"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Citadel(BaseModel):
    """A fortified place that accepts no incoming edges (inbound block test)."""

    ENTITY_TYPE: ClassVar[str] = "citadel"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "fortification": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "fortification"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Citadels can PROTECTS locations
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "location"}],
            "edges": [{"type": "PROTECTS"}],
        },
    ]

    # Citadels block ALL inbound edges (empty list)
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = []

    name = models.CharField(max_length=255, blank=True, default="")
    fortification = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_citadel"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class Wanderer(BaseModel):
    """An unconstrained entity for testing (no OUTBOUND_EDGES or INBOUND_EDGES).

    Since neither constraint is defined, a Wanderer can form or receive
    any edge type to/from any node type.
    """

    ENTITY_TYPE: ClassVar[str] = "wanderer"
    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "journey": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "journey"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # No OUTBOUND_EDGES defined = no restrictions
    # No INBOUND_EDGES defined = no restrictions

    name = models.CharField(max_length=255, blank=True, default="")
    journey = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_wanderer"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
