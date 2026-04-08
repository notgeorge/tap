"""GRIFT Subgraph serializers — canonical graph envelope shapes for TAP.

Implements the three subgraph return layers defined by spec-grift-subgraph:

  lite      Entity-envelope data only; lightweight graph identity and structure.
  full      Complete canonical GRIFT member shape (entity + typed payload).
  extended  Full shape plus derived presentation metadata (icon, shape, url_id).

Entry points:
  serialize_subgraph(entities, edges, *, layer, db_alias) -> {nodes, edges}
  Individual serializers for fine-grained control.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Literal

from django.utils.text import slugify

if TYPE_CHECKING:
    from collections.abc import Iterable

    from tap_grid.models import BaseModel, Edge, Entity

SubgraphLayer = Literal["lite", "full", "extended"]


# ---------------------------------------------------------------------------
# Entity envelope — shared by all layers
# ---------------------------------------------------------------------------


def serialize_entity_envelope(entity: Entity) -> dict[str, Any]:
    """Serialize the Entity spine row to a canonical envelope dict."""
    return {
        "entity_id": str(entity.pk),
        "entity_type": entity.entity_type,
        "name": entity.name,
        "dimensions": entity.dimensions,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
        "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        "deleted_at": entity.deleted_at.isoformat() if entity.deleted_at else None,
    }


# ---------------------------------------------------------------------------
# Node payload — typed model fields from FIELD_SCHEMA
# ---------------------------------------------------------------------------


def serialize_node_payload(typed_model: BaseModel) -> dict[str, Any]:
    """Extract typed model fields declared in FIELD_SCHEMA."""
    result: dict[str, Any] = {}
    for field_name in typed_model.FIELD_SCHEMA:
        value = getattr(typed_model, field_name, None)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[field_name] = value
    return result


# ---------------------------------------------------------------------------
# Node serializers — lite / full / extended
# ---------------------------------------------------------------------------


def serialize_node_lite(entity: Entity) -> dict[str, Any]:
    """Lite layer: flat entity-envelope fields only."""
    return serialize_entity_envelope(entity)


def serialize_node_full(
    entity: Entity,
    typed_model: BaseModel | None = None,
) -> dict[str, Any]:
    """Full layer: canonical nested GRIFT node object."""
    return {
        "entity": serialize_entity_envelope(entity),
        "node": serialize_node_payload(typed_model) if typed_model else {},
    }


def serialize_node_extended(
    entity: Entity,
    typed_model: BaseModel | None = None,
    *,
    icon_url: str = "",
    display: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extended layer: full shape plus presentation metadata."""
    entity_id = str(entity.pk)
    slug = slugify(entity.name) or "entity"
    disp = display or {}
    return {
        "entity": serialize_entity_envelope(entity),
        "node": serialize_node_payload(typed_model) if typed_model else {},
        "icon_url": icon_url,
        "shape": disp.get("shape", "ellipse"),
        "display": disp,
        "url_id": f"{slug}--{entity_id}",
    }


# ---------------------------------------------------------------------------
# Edge serializers — lite / full / extended
# ---------------------------------------------------------------------------


def serialize_edge_lite(edge: Edge) -> dict[str, Any]:
    """Lite layer: flat edge relationship fields."""
    return {
        "entity_id": str(edge.entity_id),
        "from_entity_id": str(edge.from_entity_id),
        "to_entity_id": str(edge.to_entity_id),
        "edge_type": edge.edge_type,
        "properties": edge.properties,
    }


def serialize_edge_full(edge: Edge) -> dict[str, Any]:
    """Full layer: canonical nested GRIFT edge object.

    Requires edge.entity to be available (use select_related("entity")).
    """
    return {
        "entity": serialize_entity_envelope(edge.entity),
        "edge": {
            "from_entity_id": str(edge.from_entity_id),
            "to_entity_id": str(edge.to_entity_id),
            "edge_type": edge.edge_type,
            "properties": edge.properties,
        },
    }


def serialize_edge_extended(
    edge: Edge,
    *,
    from_name: str = "",
    to_name: str = "",
) -> dict[str, Any]:
    """Extended layer: full shape plus endpoint display names."""
    return {
        "entity": serialize_entity_envelope(edge.entity),
        "edge": {
            "from_entity_id": str(edge.from_entity_id),
            "to_entity_id": str(edge.to_entity_id),
            "edge_type": edge.edge_type,
            "properties": edge.properties,
        },
        "from_name": from_name,
        "to_name": to_name,
    }


# ---------------------------------------------------------------------------
# Batch resolution helpers
# ---------------------------------------------------------------------------


def batch_resolve_typed_models(
    entities: Iterable[Entity],
    db_alias: str,
) -> dict[str, Any]:
    """Resolve entities to typed model instances in batch.

    Groups by entity_type and issues one query per type.
    Skips entity_type="edge" (edges are resolved separately).

    Returns:
        {entity_id_str: typed_model_instance}
    """
    from tap_grid.registry import get_model_class

    by_type: dict[str, list[uuid.UUID]] = defaultdict(list)
    for entity in entities:
        if entity.entity_type != "edge":
            by_type[entity.entity_type].append(entity.pk)

    result: dict[str, Any] = {}
    for entity_type, pks in by_type.items():
        try:
            model_cls = get_model_class(entity_type)
        except KeyError:
            continue
        for obj in model_cls.objects.using(db_alias).filter(entity_id__in=pks):
            result[str(obj.entity_id)] = obj
    return result


def batch_resolve_icon_urls(entity_type_slugs: set[str]) -> dict[str, str]:
    """Resolve icon URLs for a set of entity type slugs in batch.

    Returns:
        {slug: url_string} — empty string for types with no icon.
    """
    from tap_grid.icon import resolve_icon_url
    from tap_grid.models import EntityType

    if not entity_type_slugs:
        return {}
    return {et.slug: resolve_icon_url(et) or "" for et in EntityType.objects.filter(slug__in=entity_type_slugs)}


def batch_resolve_display(entity_type_slugs: set[str]) -> dict[str, dict[str, Any]]:
    """Resolve full tap_viz display metadata for a set of entity type slugs.

    Returns the complete ``DEFAULT_DISPLAY.get("tap_viz", {})`` dict per slug,
    making shape, nesting, and any future display concerns transparent.

    Returns:
        {slug: tap_viz_display_dict}
    """
    from tap_grid.registry import get_model_class

    result: dict[str, dict[str, Any]] = {}
    for slug in entity_type_slugs:
        try:
            model_cls = get_model_class(slug)
            result[slug] = model_cls.DEFAULT_DISPLAY.get("tap_viz", {})
        except KeyError:
            result[slug] = {}
    return result


def batch_resolve_entity_names(
    entity_ids: set[str],
    db_alias: str,
) -> dict[str, str]:
    """Resolve entity display names for a set of entity IDs in batch.

    Returns:
        {entity_id_str: name}
    """
    from tap_grid.models import Entity

    if not entity_ids:
        return {}
    return {str(e.pk): e.name for e in Entity.objects.using(db_alias).filter(pk__in=entity_ids).only("id", "name")}


# ---------------------------------------------------------------------------
# Subgraph convenience function
# ---------------------------------------------------------------------------


def serialize_subgraph(
    entities: list[Entity],
    edges: list[Edge],
    *,
    layer: SubgraphLayer = "full",
    db_alias: str = "default",
) -> dict[str, Any]:
    """Serialize entities and edges into a canonical GRIFT subgraph envelope.

    Handles all batch resolution internally based on the requested layer.

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    if layer == "lite":
        return {
            "nodes": [serialize_node_lite(e) for e in entities],
            "edges": [serialize_edge_lite(e) for e in edges],
        }

    # full and extended both need typed models.
    typed_models = batch_resolve_typed_models(entities, db_alias)

    if layer == "full":
        return {
            "nodes": [serialize_node_full(e, typed_models.get(str(e.pk))) for e in entities],
            "edges": [serialize_edge_full(e) for e in edges],
        }

    # extended — resolve presentation metadata.
    slugs = {e.entity_type for e in entities if e.entity_type != "edge"}
    icon_map = batch_resolve_icon_urls(slugs)
    display_map = batch_resolve_display(slugs)

    # Edge endpoint names.
    endpoint_ids: set[str] = set()
    for edge in edges:
        endpoint_ids.add(str(edge.from_entity_id))
        endpoint_ids.add(str(edge.to_entity_id))
    name_map = batch_resolve_entity_names(endpoint_ids, db_alias)

    return {
        "nodes": [
            serialize_node_extended(
                e,
                typed_models.get(str(e.pk)),
                icon_url=icon_map.get(e.entity_type, ""),
                display=display_map.get(e.entity_type, {}),
            )
            for e in entities
        ],
        "edges": [
            serialize_edge_extended(
                e,
                from_name=name_map.get(str(e.from_entity_id), ""),
                to_name=name_map.get(str(e.to_entity_id), ""),
            )
            for e in edges
        ],
    }
