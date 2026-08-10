"""Null-preparation semantics shared by the service write path and the GRIFT importer.

One implementation of req-grid-service-write-observation-2's lenient null rule,
importable from BOTH sides of the services gateway: the service layer prepares
payloads at write time (``tap_grid.services._impl``), and the GRIFT importer's
pre-validation must apply the SAME preparation before validating — otherwise the
importer rejects batches the service layer would accept moments later (the
2026-08-10 aws_core graceful-missing-None rejection). Lives below both callers
per the push-shared-mechanics-down rule; the importer must never import
``services._impl`` directly (service-boundary import-encapsulation guard).
"""

from __future__ import annotations

from typing import Any


def schema_permits_null(prop_schema: dict[str, Any]) -> bool:
    """True when a property schema's ``type`` declaration permits null."""
    type_decl = prop_schema.get("type")
    if isinstance(type_decl, list):
        return "null" in type_decl
    return type_decl == "null"


def prepare_null_payload(payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Drop an explicit null only on a known field that does not permit null.

    Preserves explicit null on null-permitting fields (so it clears the field and
    stamps FLIP, req-grid-service-write-observation-1) and on unknown fields (so
    additionalProperties:False still rejects them). A null on a known non-null field
    is dropped — treated as absent — preserving lenient behavior
    (req-grid-service-write-observation-2).
    """
    props: dict[str, Any] = schema.get("properties", {})
    prepared: dict[str, Any] = {}
    for field_name, value in payload.items():
        if value is None and field_name in props and not schema_permits_null(props[field_name]):
            continue
        prepared[field_name] = value
    return prepared
