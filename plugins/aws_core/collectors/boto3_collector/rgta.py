"""Resource Groups Tagging API sweep — the RGTA-primary tag path.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-tags, ACIDs -2 and -7).

One paginated ``resourcegroupstaggingapi:GetResources`` call per swept
region, scoped by ``ResourceTypeFilters``, building an
``{ResourceARN: {str: str}}`` map. RGTA only ever returns tagged (or
ever-tagged) resources, so a node absent from the map is simply untagged —
``tags = map.get(arn, {})`` is the correct answer. RGTA *decorates*
nodes discovered by the per-service enumerate path; it never drives
discovery (``req-aws-collector-tags-2``).

Operational contract (``req-aws-collector-tags-7``): the botocore
paginator handles ``PaginationToken``; a ``PaginationTokenExpiredException``
(token TTL is 15 min) restarts the whole sweep once — never resumes
mid-iteration — then fails loud. Throttling backoff is the client's
standard retry mode (configured by the caller). ``ResourceTypeFilters``
only (never ``ResourceARNList``); our filter set is far under the 100 cap.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from .tags import normalize_tags

RGTA_SERVICE = "resourcegroupstaggingapi"


def rgta_resource_type_filters(entries: list[dict[str, Any]]) -> list[str]:
    """The sorted unique ``resource_type_filter`` set across rgta entries."""
    filters = {
        e["tags"]["resource_type_filter"]
        for e in entries
        if (e.get("tags") or {}).get("source") == "rgta"
    }
    return sorted(filters)


def _sweep_once(client: Any, resource_type_filters: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    paginator = client.get_paginator("get_resources")
    for page in paginator.paginate(ResourceTypeFilters=resource_type_filters):
        for mapping in page.get("ResourceTagMappingList", []):
            arn = mapping.get("ResourceARN")
            if arn:
                # RGTA's shape is always list[{Key,Value}].
                out[arn] = normalize_tags(mapping.get("Tags", []), "list_kv")
    return out


def sweep_tags(
    client: Any, resource_type_filters: list[str]
) -> dict[str, dict[str, str]]:
    """Return ``{ResourceARN: {str: str}}`` for one region.

    Restarts the whole sweep once on ``PaginationTokenExpiredException``
    (the token is invalid after 15 min; resuming is impossible), then
    propagates.

    Args:
        client: A bound ``resourcegroupstaggingapi`` client (the caller
            sets the region and standard-retry/backoff config).
        resource_type_filters: RGTA ``service[:type]`` tokens to scope to.
    """
    if not resource_type_filters:
        return {}
    try:
        return _sweep_once(client, resource_type_filters)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code == "PaginationTokenExpiredException":
            return _sweep_once(client, resource_type_filters)  # restart, once
        raise
