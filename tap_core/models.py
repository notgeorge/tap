"""
TAP Core Models — Entity, Edge, EntityType, BaseModel, User.

Design philosophy: See DESIGN.md in this directory.
"""

import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from tap_core.icon_types import IconReference, IconType


def get_default_grid_id() -> uuid.UUID | None:
    """Return this installation's Grid ID from settings, or None if unset."""
    grid_id_str: str = getattr(settings, "TAP_GRID_ID", "")
    if grid_id_str:
        return uuid.UUID(grid_id_str)
    return None


class User(AbstractUser):
    """Custom user model — extend as needed without migration pain."""

    class Meta:
        db_table = "tap_user"


class Entity(models.Model):
    """The atomic unit of meaning in TAP. All domain objects are entities.

    Authoritative system of record — ORM models reference Entity via FK,
    never the other way around. Conceptually similar to Wikidata items.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    entity_type = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Type slug (e.g. 'server', 'control'). Validated at service layer.",
    )
    display_name = models.CharField(max_length=255, blank=True, default="")
    originating_grid_id = models.UUIDField(
        default=get_default_grid_id, null=True, blank=True, db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tap_entity"
        verbose_name_plural = "Entities"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.display_name:
            return f"{self.display_name} ({self.entity_type})"
        return f"{self.entity_type}:{self.id}"


class EntityType(models.Model):
    """Registry of entity types. Plugins populate this; Entity.entity_type
    stores the slug as a plain string (not an FK) for decoupling and speed."""

    slug = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255)
    icon = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Icon reference. Format: 'type:value' (e.g., 'named:fa-server', 'static:plugin/icon.svg')",
    )
    icon_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured icon data with type, value, and metadata. Preferred over icon CharField.",
    )
    description = models.TextField(blank=True, default="")
    plugin_name = models.CharField(max_length=255, blank=True, default="", db_index=True)

    class Meta:
        db_table = "tap_entity_type"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.display_name

    def get_icon_reference(self) -> IconReference | None:
        """Get the icon as an IconReference object.

        Prefers icon_data (structured) over icon (CharField) for backward compatibility.
        Returns None if no icon is set.
        """
        if self.icon_data:
            return IconReference.from_dict(self.icon_data)
        elif self.icon:
            return IconReference.from_string(self.icon)
        return None

    def set_icon_reference(self, icon_ref: IconReference) -> None:
        """Set the icon using an IconReference object.

        Updates both icon_data (structured) and icon (CharField) for compatibility.
        """
        self.icon_data = icon_ref.to_dict()
        self.icon = icon_ref.to_string()

    def get_icon_url(self) -> str:
        """Get the URL to access this icon.

        Returns empty string if no icon is set.
        """
        icon_ref = self.get_icon_reference()
        return icon_ref.get_url() if icon_ref else ""


class BaseModel(models.Model):
    """Abstract base for all domain ORM models (not Entity/EntityType/User).

    Enforces the TAP pattern: every domain object has an Entity.
    When tap_flip is built, realm/environment/provenance fields extend here.
    """

    entity = models.OneToOneField(
        Entity,
        on_delete=models.CASCADE,
        related_name="%(class)s",
    )
    originating_grid_id = models.UUIDField(
        default=get_default_grid_id, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Edge(BaseModel):
    """Directed, typed relationship between two entities.

    Edges ARE entities (inherit BaseModel → OneToOne to Entity).
    "No edges between edges" is a service-layer rule, not a schema constraint.
    """

    from_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="edges_out",
    )
    to_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="edges_in",
    )
    edge_type = models.CharField(max_length=255, db_index=True)
    properties = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_edge"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["from_entity", "edge_type"], name="idx_edge_from_type"),
            models.Index(fields=["to_entity", "edge_type"], name="idx_edge_to_type"),
        ]

    def __str__(self) -> str:
        return f"{self.from_entity_id} --[{self.edge_type}]--> {self.to_entity_id}"
