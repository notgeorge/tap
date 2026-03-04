"""
TAP Core Models — Entity, Edge, EntityType, BaseModel, User.

Design philosophy: See DESIGN.md in this directory.
"""

import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.utils import timezone


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
    dimensions = models.JSONField(
        default=dict,
        help_text="Flat namespace dict for partitioning/scoping (e.g. {'tap.graph': 'web'}).",
    )
    originating_grid_id = models.UUIDField(
        default=get_default_grid_id,
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tap_entity"
        verbose_name_plural = "Entities"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(fields=["dimensions"], name="idx_entity_dimensions_gin"),
        ]

    def __str__(self) -> str:
        if self.display_name:
            return f"{self.display_name} ({self.entity_type})"
        return f"{self.entity_type}:{self.id}"

    def resolve(self) -> "BaseModel":
        """Return the concrete typed model instance for this Entity.

        Uses the model registry populated at class-definition time.
        Raises KeyError if the entity_type is not registered.
        """
        from tap_grid.registry import get_model_class

        model_cls = get_model_class(self.entity_type)
        return model_cls.objects.get(entity_id=self.pk)


class EntityType(models.Model):
    """Registry of entity types. Plugins populate this; Entity.entity_type
    stores the slug as a plain string (not an FK) for decoupling and speed."""

    slug = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255)
    icon = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    plugin_name = models.CharField(max_length=255, blank=True, default="", db_index=True)

    class Meta:
        db_table = "tap_entity_type"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.display_name


class BaseModel(models.Model):
    """Abstract base for all domain ORM models (not Entity/EntityType/User).

    Enforces the TAP pattern: every domain object has a corresponding Entity
    on the Entity Spine. Concrete subclasses must declare:

        ENTITY_TYPE: ClassVar[str] = "<slug>"

    This drives auto-Entity creation on save, model registry lookup, and
    entity-type validation. Saving a concrete subclass that omits ENTITY_TYPE
    raises ImproperlyConfigured.

    Edge constraints:
        Subclasses can define OUTBOUND_EDGES and INBOUND_EDGES to constrain
        which edge types can connect to which node types. See constraints.py.

    FLIP integration:
        Subclasses can define FLIP_CONFIG to enable history tracking and
        other provenance features. See tap_flip.config for defaults.
    """

    ENTITY_TYPE: ClassVar[str]
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]]

    entity = models.OneToOneField(
        Entity,
        on_delete=models.CASCADE,
        related_name="%(class)s",
    )
    batch_id = models.CharField(
        max_length=36,
        blank=True,
        default="",
        db_index=True,
        help_text="UUIDv7 of the batch this change was included in (FLIP Phase 2).",
    )

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        # Register in the entity model registry if this subclass declares ENTITY_TYPE
        # in its own class body (not inherited). Abstract subclasses omit ENTITY_TYPE.
        entity_type = cls.__dict__.get("ENTITY_TYPE")
        if entity_type is not None:
            from tap_grid.registry import register_entity_type

            register_entity_type(entity_type, cls)

        # Register edge constraints. Use ENTITY_TYPE when declared; fall back to
        # class name for abstract intermediaries that define edge shapes.
        constraint_type = entity_type or cls.__name__.lower()
        outbound = getattr(cls, "OUTBOUND_EDGES", None)
        inbound = getattr(cls, "INBOUND_EDGES", None)
        if outbound is not None or inbound is not None:
            from tap_grid.constraints import register_constraints

            register_constraints(constraint_type, outbound, inbound)

        # FLIP: Cache config in registry (history registration deferred to app ready)
        from tap_flip.config import get_model_flip_config

        get_model_flip_config(cls)

    def get_display_name(self) -> str:
        """Return the display name for the auto-created Entity.

        Defaults to empty string. Subclasses may override to provide a
        meaningful label without requiring callers to set it explicitly.
        """
        return ""

    def _confirm_entity(self) -> None:
        """Validate that the attached Entity exists and has the correct entity_type.

        Called on save when entity_id is already set (explicit-entity path).
        Raises ValueError if the entity is missing or its type doesn't match.
        """
        entity_type = self.ENTITY_TYPE
        if not Entity.objects.filter(pk=self.entity_id, entity_type=entity_type).exists():
            raise ValueError(
                f"Entity {self.entity_id} does not exist on the spine or its "
                f"entity_type does not match '{entity_type}' "
                f"(required by {self.__class__.__name__})."
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the model, auto-creating its Entity if one is not already set.

        - No entity set: creates Entity atomically with this save (transaction.atomic).
        - Entity already set: confirms it exists and has the correct entity_type.
        """
        entity_type = getattr(self.__class__, "ENTITY_TYPE", None)
        if entity_type is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must declare ENTITY_TYPE: ClassVar[str]."
            )

        if self.entity_id is None:
            with transaction.atomic():
                base_dims = dict(getattr(self.__class__, "DEFAULT_DIMENSIONS", {}))
                caller_dims: dict[str, str] = getattr(self, "_initial_dimensions", {})
                self.entity = Entity.objects.create(
                    entity_type=entity_type,
                    display_name=self.get_display_name(),
                    dimensions={**base_dims, **caller_dims},
                )
                super().save(*args, **kwargs)
        else:
            self._confirm_entity()
            super().save(*args, **kwargs)
            Entity.objects.filter(pk=self.entity_id).update(updated_at=timezone.now())


class Edge(BaseModel):
    """Directed, typed relationship between two entities.

    Edges ARE entities (inherit BaseModel → OneToOne to Entity).
    "No edges between edges" is a service-layer rule, not a schema constraint.
    """

    ENTITY_TYPE: ClassVar[str] = "edge"

    from_entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="edges_out",
    )
    to_entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="edges_in",
    )
    edge_type = models.CharField(max_length=255, db_index=True)
    properties = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_edge"
        ordering = ["-entity__created_at"]
        indexes = [
            models.Index(fields=["from_entity", "edge_type"], name="idx_edge_from_type"),
            models.Index(fields=["to_entity", "edge_type"], name="idx_edge_to_type"),
        ]

    def __str__(self) -> str:
        return f"{self.from_entity_id} --[{self.edge_type}]--> {self.to_entity_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Validate endpoints and inherit dimensions before delegating to BaseModel.save().

        On the auto-creation path (entity_id is None):
        - Confirms both endpoints reference existing Entity rows.
        - Resolves the source node's DEFAULT_DIMENSIONS and sets _initial_dimensions
          so BaseModel.save() applies them to the backing Entity (req-grid-dimension-dc-4).
        Raises ValueError if either endpoint is missing.
        """
        if self.entity_id is None:
            # Validate from_entity exists; fetch entity_type for dimension inheritance
            from_row = Entity.objects.filter(pk=self.from_entity_id).values("entity_type").first()
            if from_row is None:
                raise ValueError(
                    f"Edge.from_entity {self.from_entity_id} does not exist on the spine."
                )
            if not Entity.objects.filter(pk=self.to_entity_id).exists():
                raise ValueError(
                    f"Edge.to_entity {self.to_entity_id} does not exist on the spine."
                )

            # Inherit DEFAULT_DIMENSIONS from source node's model class
            from tap_grid.registry import get_model_class

            try:
                source_cls = get_model_class(from_row["entity_type"])
                source_defaults = dict(getattr(source_cls, "DEFAULT_DIMENSIONS", {}))
            except KeyError:
                source_defaults = {}

            if source_defaults:
                caller_dims: dict[str, str] = getattr(self, "_initial_dimensions", {})
                self._initial_dimensions = {**source_defaults, **caller_dims}

        super().save(*args, **kwargs)

    def get_display_name(self) -> str:
        """Generate a readable label from the edge's endpoints and type."""
        return f"{self.from_entity_id} --[{self.edge_type}]--> {self.to_entity_id}"


class Dimension(BaseModel):
    """First-class graph node representing a named dimension.

    Dimension nodes allow dimensions to participate in the graph — they can
    be referenced by entity ID, queried, and connected to other entities via
    edges. Every Dimension instance is tagged with {"tap.meta": "dimension"}
    so it is always self-identifying regardless of which dimension it describes.
    """

    ENTITY_TYPE: ClassVar[str] = "dimension"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.meta": "dimension"}

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "tap_dimension"

    def __str__(self) -> str:
        return self.name
