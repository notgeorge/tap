"""Declarative edge emission for the boto3 collector (phase two).

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-edges).

Nodes are emitted first, then edges in a separate pass. Because endpoints
resolve by deterministic identity (:mod:`.identity`), the edge pass needs no
per-target lookup and an edge may be emitted before its target is collected
(GRIFT's permissive dangling-edge mode resolves it on a later run).

Each manifest edge rule declares ``value_path`` (a jsonpath into the item —
scalar or list; a list fans out one edge per element), ``target_type``,
``key_kind``, ``edge_type``, ``direction``, and an optional ``transform`` (a
*named, registered* callable mapping the raw value to the target's natural
key — never code from manifest data, mirroring ``req-aws-collector-source-3``).

This module is the **single chokepoint** for the v0-fence gap: an edge whose
``target_type`` is not a type this collector models is dropped with a
structured warning, never a run failure (``req-aws-collector-edges-6``). Edges
requiring policy-document parsing are out of v0 scope and are simply not
declared in the manifest (``req-aws-collector-edges-5``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .identity import edge_entity_id, node_entity_id
from .paths import eval_path
from .projection import ProjectedNode


class EdgeError(Exception):
    """An edge rule named a transform that is not registered."""


# A transform maps a raw extracted value to the target's natural key. It may
# return a scalar or a list (further fan-out). Specific transforms are
# registered by the fan-out increment, not here.
Transform = Callable[[Any], Any]


class TransformRegistry:
    """Plugin-local registry of edge ``transform`` callables.

    The manifest names a transform; the engine resolves it here. Code is
    never imported from manifest data (mirrors ``req-aws-collector-source-3``).
    """

    def __init__(self) -> None:
        self._fns: dict[str, Transform] = {}

    def register(self, name: str, fn: Transform) -> None:
        """Register ``fn`` under ``name`` (last registration wins)."""
        self._fns[name] = fn

    def get(self, name: str) -> Transform:
        """Resolve a registered transform or raise ``EdgeError``."""
        try:
            return self._fns[name]
        except KeyError:
            known = ", ".join(sorted(self._fns)) or "<none>"
            raise EdgeError(
                f"edge transform {name!r} is not registered (known: {known})"
            ) from None


@dataclass(frozen=True)
class EdgeEmission:
    """Result of the edge pass for one node: envelopes + drop warnings.

    ``warnings`` are structured drop messages the runtime feeds to
    ``record_warn`` — one per dropped rule, not per fanned-out value.
    """

    envelopes: list[dict[str, Any]]
    warnings: list[str]


def _as_value_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    return [v for v in values if v is not None and v != ""]


def emit_edges(
    node: ProjectedNode,
    entry: dict[str, Any],
    *,
    modeled_types: set[str],
    transforms: TransformRegistry,
    dimensions: dict[str, str],
) -> EdgeEmission:
    """Emit GRIFT edge envelopes for one projected node.

    Args:
        node: The source node (its identity + ``ResponseMetadata``-free item).
        entry: The validated manifest entry the node came from.
        modeled_types: Entity types this collector models. An edge to a
            ``target_type`` outside this set is dropped with a warning.
        transforms: The plugin-local transform registry.
        dimensions: Dimensions stamped on every emitted edge entity.
    """
    envelopes: list[dict[str, Any]] = []
    warnings: list[str] = []

    for rule in entry.get("edges", []):
        target_type = rule["target_type"]
        if target_type not in modeled_types:
            warnings.append(
                f"{node.entity_type} {node.natural_key}: dropped "
                f"{rule['edge_type']} edge — target_type {target_type!r} is "
                f"not modeled by this collector (v0 fence)"
            )
            continue

        raw = eval_path(node.raw_item, rule["value_path"])
        transform_name = rule.get("transform")
        if transform_name:
            raw = transforms.get(transform_name)(raw)

        for value in _as_value_list(raw):
            target_key = str(value)
            target_id = node_entity_id(target_type, target_key)
            if rule["direction"] == "inbound":
                from_key, to_key = target_key, node.natural_key
                from_id, to_id = target_id, node.entity_id
            else:  # outbound
                from_key, to_key = node.natural_key, target_key
                from_id, to_id = node.entity_id, target_id

            edge_id = edge_entity_id(rule["edge_type"], from_key, to_key)
            envelopes.append(
                {
                    "entity": {
                        "entity_id": str(edge_id),
                        "entity_type": "edge",
                        "name": f"{from_key} {rule['edge_type']} {to_key}",
                        "dimensions": dimensions,
                    },
                    "edge": {
                        "from_entity_id": str(from_id),
                        "to_entity_id": str(to_id),
                        "edge_type": rule["edge_type"],
                        "properties": {},
                    },
                }
            )

    return EdgeEmission(envelopes=envelopes, warnings=warnings)
