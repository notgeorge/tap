"""
TAP Core Models — Entity, Edge, EntityType, BaseModel, User.

Design philosophy: See DESIGN.md in this directory.
"""

import uuid
from typing import Any, ClassVar

import jsonschema
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models, transaction
from django.utils import timezone


def dangerously_ignore_validator(fn: Any) -> Any:
    """Mark a validate_<field>() method as intentionally excluded from FIELD_SCHEMAS.

    Suppresses the startup invariant check that would otherwise raise
    ImproperlyConfigured when a validate_<field>() method exists but the field
    is not listed in FIELD_SCHEMAS. Use this to pre-stage validation logic
    without fully activating it.

    The name is deliberately alarming — a validator that exists but never runs
    is an unusual and potentially risky state.
    """
    fn._dangerously_ignore_validator = True
    return fn


# Django model methods that start with "validate_" but are not field validators.
# Overriding these in a subclass should not trigger the FIELD_SCHEMAS check.
_DJANGO_VALIDATE_METHODS: frozenset[str] = frozenset({"validate_unique", "validate_constraints"})


def _check_field_schemas(cls: type) -> None:
    """Enforce FIELD_SCHEMAS startup invariants at class definition time.

    Checks performed (matching req-grid-entity-validation ACIDs 2–5):
      2. Every entry has "validation": "jsonschema" or "function".
      3. "jsonschema" entries include a "schema" key.
      4. "function" entries have a matching validate_<field>() method.
      5. No validate_<field>() method in cls.__dict__ is missing from FIELD_SCHEMAS
         (unless decorated with @dangerously_ignore_validator).

    Note: ACID-6 ("keys are real fields") is deferred to full_validate() because
    Django's metaclass moves field declarations out of cls.__dict__ before
    __init_subclass__ is called, making field lookup unavailable at this point.

    Raises ImproperlyConfigured immediately on any violation.
    """
    schemas: dict[str, dict] = cls.__dict__.get("FIELD_SCHEMAS", {})

    for field_name, entry in schemas.items():
        # ACID-2: valid "validation" key
        validation = entry.get("validation")
        if validation not in ("jsonschema", "function"):
            raise ImproperlyConfigured(
                f"{cls.__name__}.FIELD_SCHEMAS['{field_name}']: "
                f'"validation" must be "jsonschema" or "function", got {validation!r}.'
            )

        # ACID-3: jsonschema entries must include "schema"
        if validation == "jsonschema" and "schema" not in entry:
            raise ImproperlyConfigured(
                f"{cls.__name__}.FIELD_SCHEMAS['{field_name}']: "
                f'"jsonschema" entry is missing required "schema" key.'
            )

        # ACID-4: function entries must have a matching validate_<field>() method
        if validation == "function":
            method = getattr(cls, f"validate_{field_name}", None)
            if not callable(method):
                raise ImproperlyConfigured(
                    f"{cls.__name__}.FIELD_SCHEMAS['{field_name}']: "
                    f'"function" validation requires a validate_{field_name}() method on the class.'
                )

    # ACID-5: every validate_<field>() defined directly on this class must be in FIELD_SCHEMAS
    for attr_name in cls.__dict__:
        if not attr_name.startswith("validate_"):
            continue
        if attr_name in _DJANGO_VALIDATE_METHODS:
            continue
        field_name = attr_name[len("validate_"):]
        if not field_name:
            continue
        method = getattr(cls, attr_name, None)
        if not callable(method):
            continue
        if getattr(method, "_dangerously_ignore_validator", False):
            continue
        if field_name not in schemas:
            raise ImproperlyConfigured(
                f"{cls.__name__}.{attr_name}() is defined but '{field_name}' is not in "
                f"FIELD_SCHEMAS. Add it to FIELD_SCHEMAS or use @dangerously_ignore_validator."
            )


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
    name = models.CharField(max_length=255, blank=True, default="")
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
        if self.name:
            return f"{self.name} ({self.entity_type})"
        return f"{self.entity_type}:{self.id}"

    def resolve(self) -> BaseModel:
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
    name = models.CharField(max_length=255)
    icon = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    plugin_name = models.CharField(max_length=255, blank=True, default="", db_index=True)

    class Meta:
        db_table = "tap_entity_type"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


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
    FIELD_SCHEMAS: ClassVar[dict[str, dict]] = {}
    HOTLINKS: ClassVar[list[dict]] = []
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {}

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
        help_text="UUIDv7 of the batch this change was included in.",
    )
    flip_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="FLIP field-path-to-batch-id map: tracks which batch last set each provenance-tracked field.",
    )

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        # FIELD_SCHEMAS invariants run first — before any registry side effects.
        # If these raise, nothing has been registered and the failure is clean.
        _check_field_schemas(cls)

        # HOTLINKS invariants — only validate if this class declares HOTLINKS directly.
        if "HOTLINKS" in cls.__dict__:
            from tap_grid.hotlink import _check_hotlinks
            _check_hotlinks(cls)

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

    def get_name(self) -> str:
        """Return the name for the auto-created Entity.

        Defaults to empty string. Subclasses may override to provide a
        meaningful label without requiring callers to set it explicitly.
        The returned value is stored as Entity.name (a materialized projection
        for cross-type query efficiency).
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

    def validate(self) -> None:
        """Whole-record validation hook. Override for cross-field business rules.

        Called by full_validate() after per-field checks. Base implementation is
        a no-op. Raise ValidationError with a field-keyed dict for field errors,
        or a plain message for non-field (__all__) errors.
        """

    def full_validate(self) -> None:
        """Run all declared FIELD_SCHEMAS validators and the whole-record hook.

        Collects every error before raising so callers see the complete picture.
        Can be called without saving (req-grid-entity-validation-11).

        Raises ValidationError({field: [messages]}) if any checks fail.
        """
        errors: dict[str, list[str]] = {}
        schemas: dict[str, dict] = self.__class__.FIELD_SCHEMAS

        for field_name, entry in schemas.items():
            # ACID-6 (deferred): verify the key is actually an attribute on this instance.
            # Full field-vs-model-field distinction isn't possible at __init_subclass__ time
            # due to Django metaclass ordering; we catch it here instead.
            if not hasattr(self, field_name):
                raise ImproperlyConfigured(
                    f"{self.__class__.__name__}.FIELD_SCHEMAS: '{field_name}' is not an "
                    f"attribute of this model."
                )

            validation = entry["validation"]
            field_value = getattr(self, field_name)

            if validation == "jsonschema":
                try:
                    jsonschema.validate(instance=field_value, schema=entry["schema"])
                except jsonschema.ValidationError as exc:
                    errors.setdefault(field_name, []).append(exc.message)

            elif validation == "function":
                method = getattr(self, f"validate_{field_name}")
                try:
                    method()
                except ValidationError as exc:
                    try:
                        for key, msgs in exc.message_dict.items():
                            errors.setdefault(key, []).extend(str(m) for m in msgs)
                    except AttributeError:
                        errors.setdefault(field_name, []).extend(exc.messages)

        # Hotlink consistency check (skipped on first save when entity_id is None).
        from tap_grid.hotlink import validate_hotlinks

        try:
            validate_hotlinks(self)
        except ValidationError as exc:
            try:
                for key, msgs in exc.message_dict.items():
                    errors.setdefault(key, []).extend(str(m) for m in msgs)
            except AttributeError:
                errors.setdefault("__all__", []).extend(exc.messages)

        # Whole-record hook
        try:
            self.validate()
        except ValidationError as exc:
            try:
                for key, msgs in exc.message_dict.items():
                    errors.setdefault(key, []).extend(str(m) for m in msgs)
            except AttributeError:
                errors.setdefault("__all__", []).extend(exc.messages)

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the model, auto-creating its Entity if one is not already set.

        - No entity set: creates Entity atomically with this save (transaction.atomic).
        - Entity already set: confirms it exists and has the correct entity_type.
        - skip_validation=True: bypasses full_validate() (for migrations / fixtures).

        FLIP: update_flip_map() is called before the DB write so flip_map changes
        are always atomic with the field changes that triggered them.
        """
        skip_validation: bool = kwargs.pop("skip_validation", False)
        if not skip_validation:
            self.full_validate()

        entity_type = getattr(self.__class__, "ENTITY_TYPE", None)
        if entity_type is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must declare ENTITY_TYPE: ClassVar[str]."
            )

        # FLIP map update — mutates self.flip_map in memory before the write.
        from tap_grid.context import get_batch_id
        from tap_grid.flip import update_flip_map

        update_fields = kwargs.get("update_fields")
        changed_fields = list(update_fields) if update_fields is not None else None
        if update_flip_map(self, changed_fields, get_batch_id()):
            if update_fields is not None:
                kwargs["update_fields"] = list(update_fields) + ["flip_map"]

        if self.entity_id is None:
            with transaction.atomic():
                base_dims = dict(getattr(self.__class__, "DEFAULT_DIMENSIONS", {}))
                caller_dims: dict[str, str] = getattr(self, "_initial_dimensions", {})
                self.entity = Entity.objects.create(
                    entity_type=entity_type,
                    name=self.get_name(),
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
        """Validate endpoints, apply edge default dimensions, and validate properties.

        On the auto-creation path (entity_id is None):
        - Confirms both endpoints reference existing Entity rows.
        - Applies the edge type's registered default_dimensions to the backing Entity,
          merged with any caller-supplied _initial_dimensions (caller wins on conflict).
        Raises ValueError if either endpoint is missing.

        On every save:
        - Validates properties against the registered JSON Schema for this edge type,
          if one exists. Raises EdgePropertyValidationError on failure.
        """
        if self.entity_id is None:
            if not Entity.objects.filter(pk=self.from_entity_id).exists():
                raise ValueError(
                    f"Edge.from_entity {self.from_entity_id} does not exist on the spine."
                )
            if not Entity.objects.filter(pk=self.to_entity_id).exists():
                raise ValueError(
                    f"Edge.to_entity {self.to_entity_id} does not exist on the spine."
                )

            # Apply edge type's own default dimensions (req-grid-dimension-dc-4)
            from tap_grid.constraints import get_edge_default_dimensions

            edge_defaults = get_edge_default_dimensions(self.edge_type)
            caller_dims: dict[str, str] = getattr(self, "_initial_dimensions", {})
            merged = {**edge_defaults, **caller_dims}
            if merged:
                self._initial_dimensions = merged

        # Validate properties on every save (create and update)
        from tap_grid.constraints import validate_edge_properties

        validate_edge_properties(self.edge_type, self.properties)

        super().save(*args, **kwargs)

    def get_name(self) -> str:
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


class Search(BaseModel):
    """Reusable query definition stored as a first-class grid entity.

    A Search encapsulates everything needed to execute a repeatable TAP query:
    execution mode, root type, query definition, parameter schema, return
    preferences, and pagination configuration. Panels and other consumers
    reference Search objects rather than embedding ad hoc query logic.

    Two execution modes in v1:
        - module: delegates to a registered callable via ScopedRegistry
        - orm: compiles a declarative JSON DSL to a read-only ORM queryset
    """

    ENTITY_TYPE: ClassVar[str] = "search"

    FIELD_SCHEMAS: ClassVar[dict[str, dict]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "search_type": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": ["module", "orm"]},
        },
        "root": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": ["node", "edge"]},
        },
        "definition": {
            "validation": "jsonschema",
            "schema": {"type": "object"},
        },
    }

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    search_type = models.CharField(max_length=50)
    root = models.CharField(max_length=50)
    definition = models.JSONField(default=dict)
    input_schema = models.JSONField(null=True, blank=True)
    returns = models.JSONField(null=True, blank=True)
    default_limit = models.IntegerField(null=True, blank=True)
    max_limit = models.IntegerField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_search"

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name

    def validate(self) -> None:
        """Cross-field invariants between search_type and definition."""
        if not isinstance(self.definition, dict):
            # FIELD_SCHEMAS already flagged the type error; skip cross-field checks.
            return

        if self.search_type == "module":
            allowed_keys = {"runner_key"}
            extra = set(self.definition.keys()) - allowed_keys
            if extra:
                raise ValidationError(
                    {"definition": [f"Module definition only allows 'runner_key'; unexpected keys: {sorted(extra)}."]}
                )
            runner_key = self.definition.get("runner_key")
            if not isinstance(runner_key, str) or not runner_key:
                raise ValidationError(
                    {"definition": ["Module definition requires 'runner_key' as a non-empty string."]}
                )

        elif self.search_type == "orm":
            filters = self.definition.get("filters")
            if not isinstance(filters, dict):
                raise ValidationError({"definition": ["ORM definition requires 'filters' as a dict."]})
            hops = self.definition.get("hops")
            if hops is not None:
                if not isinstance(hops, list):
                    raise ValidationError({"definition": ["ORM 'hops' must be a list."]})
                if len(hops) > 1:
                    raise ValidationError({"definition": ["ORM definition supports at most one hop."]})
                for hop in hops:
                    if not isinstance(hop, dict):
                        raise ValidationError({"definition": ["Each hop must be a dict."]})
                    if hop.get("direction") not in ("in", "out"):
                        raise ValidationError({"definition": ["Hop 'direction' must be 'in' or 'out'."]})
                    if not isinstance(hop.get("edge_type"), str) or not hop.get("edge_type"):
                        raise ValidationError({"definition": ["Hop 'edge_type' must be a non-empty string."]})
            order_by = self.definition.get("order_by")
            if order_by is not None and not isinstance(order_by, list):
                raise ValidationError({"definition": ["ORM 'order_by' must be a list."]})
