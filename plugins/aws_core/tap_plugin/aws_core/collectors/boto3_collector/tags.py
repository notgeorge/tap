"""Canonical tag normalization for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-tags).

AWS returns tags in several wire shapes; every collected node carries one
canonical `tags` field — a flat ``{str: str}`` map. This is the single
normalization seam (the CloudQuery `TagsToMap` pattern): one helper folds
any declared shape, never a per-service loop (the drift-prone
Steampipe-style boilerplate the prior-art analysis flagged).

v0 shapes (``req-aws-collector-tags-8``), fenced to all of Sam's 8:

- ``list_kv`` — a list of ``{"Key": k, "Value": v}`` structs (the RGTA
  shape, and every per-service side-quest in scope).
- ``map`` — already a string→string object.

The ECS lowercase-``key``/``value``, CloudTrail nested, and WAFv2 wrapped
shapes are real but out of scope — named for a future enum extension.
"""

from __future__ import annotations

from typing import Any

from .paths import eval_path


class TagShapeError(Exception):
    """A manifest declared a tag shape the normalizer does not handle."""


def normalize_tags(raw: Any, shape: str) -> dict[str, str]:
    """Fold a raw AWS tag payload of ``shape`` into canonical ``{str: str}``.

    Graceful: a missing / empty / wrong-typed payload yields ``{}`` (an
    untagged resource is a normal fact, not an error).
    """
    if shape == "list_kv":
        if not isinstance(raw, list):
            return {}
        out: dict[str, str] = {}
        for element in raw:
            if isinstance(element, dict) and "Key" in element:
                out[str(element["Key"])] = str(element.get("Value", ""))
        return out
    if shape == "map":
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items()}
    raise TagShapeError(f"unsupported tag shape {shape!r} (v0: list_kv | map)")


def tags_block(entry: dict[str, Any]) -> dict[str, Any] | None:
    """The entry's ``tags`` block, or ``None`` if it declares no tags."""
    return entry.get("tags")


def rgta_join_arn(entry: dict[str, Any], item: Any) -> Any:
    """The ARN to match against RGTA ``ResourceARN`` for an ``rgta`` entry.

    ``tags.arn_from`` (a jsonpath into the enumerate item) when declared,
    else the entry's ``natural_key`` — both resolved with the restricted
    path evaluator so the existing graceful-missing contract holds.
    """
    block = entry.get("tags") or {}
    path = block.get("arn_from") or entry["natural_key"]
    return eval_path(item, path)
