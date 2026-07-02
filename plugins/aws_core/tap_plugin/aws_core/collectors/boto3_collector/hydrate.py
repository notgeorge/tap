"""The fan-out hydrate template (first of the two named engine seams).

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-hydrate).

One reusable helper, written once: for an enumerated item it runs each
manifest-declared hydrate op and assembles a self-describing configuration
envelope. The enumerate item is the envelope root; two reserved siblings are
added:

- ``_hydrate`` — the *event record*. Per slot: ``{"status", "op", "data"}``
  on success (``data`` is the verbatim response, ``ResponseMetadata``
  stripped), or ``{"status", "op", "error_code"}`` when the call returned no
  data.
- ``_hydrate_mapping`` — the *intent*. Per slot: ``{"op", "why"}``,
  materialized from the manifest so a grid object is legible without it.

Slot ``status`` is the load-bearing distinction and is **never** lossy:

- ``ok`` — succeeded; ``data`` present.
- ``absent`` — AWS "not configured" (``NoSuch*`` / ``*NotFound*``). A real,
  queryable fact: the resource genuinely has no such configuration.
- ``denied`` — ``AccessDenied`` / authorization failure. Value unknown.
  **Never** conflated with ``absent`` — "no policy" and "could not read the
  policy" are opposite compliance conclusions.
- ``error`` — unexpected / throttle-exhausted.

Each sub-call's failure is swallowed independently, so one missing
sub-config never fails the resource. Node identity is always taken from the
root enumerate item, never a hydrate slot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from botocore import xform_name
from botocore.exceptions import BotoCoreError, ClientError

from .envelope import without_response_metadata

# AWS authorization-failure codes — "could not read", value unknown.
_DENIED_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "AuthFailure",
        "Forbidden",
        "403",
    }
)


def _classify(code: str) -> str:
    """Map an AWS error code to ``absent`` | ``denied`` | ``error``."""
    if code in _DENIED_CODES:
        return "denied"
    # AWS's "not configured" signal is consistently NoSuch* / *NotFound*.
    if code.startswith("NoSuch") or code.endswith(("NotFound", "NotFoundError")):
        return "absent"
    return "error"


def hydrate_item(
    client: Any,
    item: Mapping[str, Any],
    hydrate_ops: Sequence[Mapping[str, str]],
    *,
    call_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the declared hydrate ops for one item; return the envelope.

    Args:
        client: A boto3 client bound to the item's region.
        item: The raw enumerate item (the envelope root).
        hydrate_ops: The manifest entry's ``hydrate`` list (``key/op/why``).
        call_kwargs: The identifier kwargs every hydrate op takes (the
            per-service binding the composing ``custom_fn`` supplies, e.g.
            ``{"Bucket": name}``).
    """
    envelope = dict(item)
    record: dict[str, Any] = {}
    mapping: dict[str, Any] = {}

    for slot in hydrate_ops:
        key, op, why = slot["key"], slot["op"], slot["why"]
        mapping[key] = {"op": op, "why": why}
        try:
            response = getattr(client, xform_name(op))(**call_kwargs)
            record[key] = {
                "status": "ok",
                "op": op,
                "data": without_response_metadata(response),
            }
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "")) or "Unknown"
            record[key] = {"status": _classify(code), "op": op, "error_code": code}
        except BotoCoreError as exc:
            record[key] = {
                "status": "error",
                "op": op,
                "error_code": type(exc).__name__,
            }

    envelope["_hydrate"] = record
    envelope["_hydrate_mapping"] = mapping
    return envelope
