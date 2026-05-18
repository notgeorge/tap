"""Configuration envelope + deterministic serialization for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-field-projection "Reserved envelope keys and stable
serialization").

Two engine rules keep a node's ``configuration`` byte-identical across runs
when the resource is unchanged (so re-runs upsert cleanly and History/FLIP
does not churn):

1. ``ResponseMetadata`` is stripped from every boto3 response before it
   becomes an item / ``configuration`` — it carries request ids, retry
   counts, and timestamped headers that would otherwise change every run.
2. Values are normalized deterministically: ``datetime``/``date`` ->
   ISO 8601 UTC (``...Z``); the engine serializes with sorted keys.

The node ``configuration`` is the enumerate item at its root plus the
engine-reserved ``_source`` ({op, why}); ``_hydrate`` / ``_hydrate_mapping``
are added by the fan-out seam (later). ``_source`` is present on every node
so even a single-call object is self-describing without the manifest.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def without_response_metadata(response: Any) -> Any:
    """Return ``response`` minus a top-level ``ResponseMetadata`` key."""
    if isinstance(response, dict):
        return {k: v for k, v in response.items() if k != "ResponseMetadata"}
    return response


def jsonable(value: Any) -> Any:
    """Recursively normalize a value to a deterministic, JSON-safe form.

    ``datetime``/``date`` -> ISO 8601 UTC ``...Z``; tz-naive datetimes are
    assumed UTC. dict/list recurse; scalars pass through; anything else falls
    back to ``str()`` (AWS payloads are JSON + datetime, so this is rare).
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_configuration(item: Any, *, source_op: str, why: str) -> dict[str, Any]:
    """Build a node's ``configuration``: the item at root + reserved ``_source``.

    ``item`` is the raw enumerate item (already free of ``ResponseMetadata``).
    The result is deterministic and JSON-safe.
    """
    config = jsonable(item)
    if not isinstance(config, dict):
        config = {"value": config}
    config["_source"] = {"op": source_op, "why": why}
    return config
