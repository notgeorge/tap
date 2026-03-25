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
from simple_history.models import HistoricalRecords

from tap_flip.history.context import get_history_user
from tap_grid.models import BaseModel


class Character(BaseModel):
    """A being in Middle-earth (Frodo, Gandalf, Sauron, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "character"
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "ellipse"}}
    # History is enabled directly via the HistoricalRecords manager below.
    FLIP_CONFIG: ClassVar[dict[str, Any]] = {
        "batch": {"enabled": True},
        "flip": {"enabled": True, "fields": ["bio", "title"]},
    }

    history = HistoricalRecords(get_user=get_history_user)

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

    bio = models.TextField(blank=True, default="")
    title = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_character"

    def __str__(self) -> str:
        return self.entity.name


class Location(BaseModel):
    """A place in Middle-earth (Shire, Mordor, Rivendell, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "location"
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

    description = models.TextField(blank=True, default="")
    realm = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_location"

    def __str__(self) -> str:
        return self.entity.name


class Artifact(BaseModel):
    """A significant object (The One Ring, Sting, Andúril, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "artifact"
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

    power = models.TextField(blank=True, default="")
    origin = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_artifact"

    def __str__(self) -> str:
        return self.entity.name


class Race(BaseModel):
    """A race of beings (Hobbit, Elf, Dwarf, Human, Wizard, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "race"
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

    homeland = models.CharField(max_length=255, blank=True, default="")
    traits = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_race"

    def __str__(self) -> str:
        return self.entity.name


class Faction(BaseModel):
    """A group or alliance (Fellowship, Mordor, Rohan, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "faction"
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

    purpose = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_faction"

    def __str__(self) -> str:
        return self.entity.name


class Sentinel(BaseModel):
    """A watcher that can reference anything (wildcard test case)."""

    ENTITY_TYPE: ClassVar[str] = "sentinel"
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

    watch_domain = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_sentinel"

    def __str__(self) -> str:
        return self.entity.name


class Citadel(BaseModel):
    """A fortified place that accepts no incoming edges (inbound block test)."""

    ENTITY_TYPE: ClassVar[str] = "citadel"
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

    fortification = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_citadel"

    def __str__(self) -> str:
        return self.entity.name


class Wanderer(BaseModel):
    """An unconstrained entity for testing (no OUTBOUND_EDGES or INBOUND_EDGES).

    Since neither constraint is defined, a Wanderer can form or receive
    any edge type to/from any node type.
    """

    ENTITY_TYPE: ClassVar[str] = "wanderer"
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # No OUTBOUND_EDGES defined = no restrictions
    # No INBOUND_EDGES defined = no restrictions

    journey = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_wanderer"

    def __str__(self) -> str:
        return self.entity.name
