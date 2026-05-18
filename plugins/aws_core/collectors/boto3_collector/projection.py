"""Field projection for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-field-projection).

Each raw item becomes a typed-node projection:

- declared model fields are extracted via the manifest's per-field jsonpaths,
  with graceful-missing semantics — an unresolved path yields ``None``, never
  a run failure (``req-aws-collector-field-projection-2``);
- the **entire raw item** is retained verbatim in ``configuration`` so no AWS
  attribute is ever lost (``req-aws-collector-field-projection-3``);
- identity is deterministic from ``(entity_type, natural_key)`` so re-runs
  upsert in place (``req-aws-collector-identity``).

No type coercion is performed beyond the engine-level datetime -> ISO 8601 UTC
rule already applied in :mod:`.envelope`; the model / service-layer validation
is the sole gate (``req-aws-collector-field-projection-4``). The optional
``created_at``/``updated_at`` envelope mapping with a format hint
(``req-aws-collector-field-projection-5``) is a later refinement and is not
declared by the v0 manifest — grid-native first-seen/updated time is the
always-present spine until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .envelope import build_configuration, without_response_metadata
from .identity import node_entity_id
from .paths import eval_path


class ProjectionError(Exception):
    """A raw item could not be projected (its natural key did not resolve).

    Identity-critical: an item with no natural key cannot form a deterministic
    node id. The runtime integration classifies this per-item (record a warn
    and skip the item) rather than failing the whole run.
    """


@dataclass(frozen=True)
class ProjectedNode:
    """A raw AWS item projected to a typed node (pre-service-layer).

    ``raw_item`` is the ``ResponseMetadata``-free item, retained so the later
    edge pass (``req-aws-collector-edges``) resolves edge value paths against
    exactly what produced this node.
    """

    entity_type: str
    entity_id: UUID
    natural_key: str
    name: str
    fields: dict[str, Any]
    configuration: dict[str, Any]
    raw_item: Any


def source_op_label(entry: dict[str, Any]) -> str:
    """The ``_source.op`` label: the ``aws_op`` or the ``custom_fn`` name."""
    source = entry["source"]
    return str(source.get("aws_op") or source["custom_fn"])


def project_item(entry: dict[str, Any], item: Any) -> ProjectedNode:
    """Project one raw item into a :class:`ProjectedNode`.

    Args:
        entry: A validated manifest entry.
        item: One raw resource item yielded by the entry's source.

    Raises:
        ProjectionError: The entry's ``natural_key`` path did not resolve.
    """
    item = without_response_metadata(item)

    natural_key = eval_path(item, entry["natural_key"])
    if natural_key is None or natural_key == "":
        raise ProjectionError(
            f"{entry['entity_type']}: natural_key {entry['natural_key']!r} "
            f"did not resolve on the item"
        )
    natural_key = str(natural_key)

    fields = {
        model_field: eval_path(item, path)
        for model_field, path in entry["fields"].items()
    }
    name = fields.get("name") or natural_key

    return ProjectedNode(
        entity_type=entry["entity_type"],
        entity_id=node_entity_id(entry["entity_type"], natural_key),
        natural_key=natural_key,
        name=str(name),
        fields=fields,
        configuration=build_configuration(
            item, source_op=source_op_label(entry), why=entry["why"]
        ),
        raw_item=item,
    )
