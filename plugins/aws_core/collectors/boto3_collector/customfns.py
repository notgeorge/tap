"""Registered ``custom_fn`` callables for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-source / req-aws-collector-hydrate).

A ``custom_fn`` is the thin per-service glue for resources AWS cannot
enumerate richly in one call. It composes the reusable :func:`hydrate_item`
template (it does not hand-roll multi-call logic) and yields raw items in the
same shape an ``aws_op`` would. Code is never loaded from manifest data; the
manifest only names the callable.

S3 is the worst-case fan-out the seam exists for: ``ListBuckets`` returns a
few fields and the compliance-relevant state comes from independent
per-bucket ``GetBucket*`` calls. The hydrate op list lives in the manifest
(``req-aws-collector-hydrate-3``); this glue only supplies the S3-specific
identifier binding (``Bucket=<name>``) and per-bucket region routing (S3
redirects ``GetBucket*`` to the bucket's own region).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from .envelope import without_response_metadata
from .hydrate import hydrate_item
from .manifest import manifest_entries
from .source import CustomFnRegistry


def _s3_hydrate_ops() -> list[dict[str, str]]:
    """The manifest-declared S3 hydrate list (manifest is the source)."""
    for entry in manifest_entries():
        if entry["entity_type"] == "aws_s3_bucket":
            ops: list[dict[str, str]] = entry.get("hydrate", [])
            return ops
    return []


def s3_buckets_hydrated(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Enumerate S3 buckets and fan out each bucket's compliance sub-config.

    Yields one envelope per bucket: the ``ListBuckets`` item at the root
    (carrying ``BucketArn`` — the stable natural key) plus the
    ``_hydrate`` / ``_hydrate_mapping`` siblings the template assembles.
    """
    base = session.client("s3")
    listing = without_response_metadata(base.list_buckets())
    hydrate_ops = _s3_hydrate_ops()

    for bucket in listing.get("Buckets", []):
        name = bucket.get("Name")
        # GetBucket* is region-bound (S3 redirects otherwise); resolve the
        # bucket's region from the global endpoint, then bind a regional
        # client for the fan-out.
        try:
            location = base.get_bucket_location(Bucket=name)
            region = location.get("LocationConstraint") or "us-east-1"
        except ClientError, BotoCoreError:
            region = "us-east-1"
        regional = session.client("s3", region_name=region)
        yield hydrate_item(regional, bucket, hydrate_ops, call_kwargs={"Bucket": name})


def _pages(client: Any, method: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
    """Yield response pages for ``method``, paginated when botocore can.

    Mirrors :func:`.source.iter_aws_op`'s paginate-or-single robustness,
    with ``ResponseMetadata`` stripped per page.
    """
    if client.can_paginate(method):
        for page in client.get_paginator(method).paginate(**kwargs):
            yield without_response_metadata(page)
        return
    yield without_response_metadata(getattr(client, method)(**kwargs))


def route53_zones_with_alias_targets(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Enumerate Route 53 hosted zones, resolving CloudFront alias targets.

    Route 53's ``ListHostedZones`` is shallow; the routing relationship
    lives in each zone's record sets, where an A/AAAA *alias* whose
    ``AliasTarget.DNSName`` is a CloudFront distribution domain expresses
    "this zone routes traffic to that distribution". The edge target
    (``aws_cloudfront_distribution``) is ARN-keyed, but a record set only
    carries the CloudFront *domain* — bridging domain -> ARN is a
    cross-resource join no pure scalar transform can do. That join is
    exactly what this ``custom_fn`` seam exists for: it lists CloudFront
    once, builds a ``domain -> ARN`` map, and yields each zone enriched
    with the resolved ``alias_cloudfront_arns`` so ``ROUTES_TRAFFIC``
    resolves by deterministic identity with no transform (the make-it-work
    natural-key discipline; req-aws-collector-edges-7). The raw
    ``alias_cloudfront_domains`` stay lossless in ``configuration``.

    CloudFront and Route 53 are global; clients are bound to ``us-east-1``
    per the global-resource region invariant.
    """
    cf = session.client("cloudfront", region_name="us-east-1")
    arn_by_domain: dict[str, str] = {}
    for page in _pages(cf, "list_distributions"):
        for dist in (page.get("DistributionList", {}) or {}).get("Items", []) or []:
            domain = (dist.get("DomainName") or "").rstrip(".").lower()
            arn = dist.get("ARN")
            if domain and arn:
                arn_by_domain[domain] = arn

    r53 = session.client("route53", region_name="us-east-1")
    for zpage in _pages(r53, "list_hosted_zones"):
        for zone in zpage.get("HostedZones", []):
            zone_id = zone.get("Id")
            domains: list[str] = []
            arns: list[str] = []
            for rpage in _pages(r53, "list_resource_record_sets", HostedZoneId=zone_id):
                for rr in rpage.get("ResourceRecordSets", []):
                    dns = (rr.get("AliasTarget") or {}).get("DNSName") or ""
                    domain = dns.rstrip(".").lower()
                    if not domain.endswith(".cloudfront.net"):
                        continue
                    domains.append(domain)
                    arn = arn_by_domain.get(domain)
                    if arn is not None:
                        arns.append(arn)
            # Dedupe order-preserving: a zone routing to one distribution
            # via BOTH an A and an AAAA alias (the standard IPv4+IPv6
            # setup) yields the domain/ARN twice. Without dedup, edge
            # fan-out emits two edges with the same deterministic
            # edge_entity_id -> a duplicate_entity_id that GRIFT rejects
            # the whole batch over. One CF distribution -> one edge.
            yield {
                **zone,
                "alias_cloudfront_domains": list(dict.fromkeys(domains)),
                "alias_cloudfront_arns": list(dict.fromkeys(arns)),
                # Bare zone ID (last path segment of Id like "/hostedzone/Z…").
                # list_tags_for_resource wants ResourceId in this form; Id
                # itself stays as boto3 returned it so existing identity and
                # downstream consumers don't shift.
                "_zone_resource_id": (zone_id or "").rsplit("/", 1)[-1],
            }


def dynamodb_tables_described(session: Any, *, client_for: Any) -> Iterator[dict[str, Any]]:
    """Enumerate DynamoDB tables (regional) and describe each.

    ``ListTables`` returns table-name strings only — no ARN, no status,
    no billing mode. ``DescribeTable`` per name is the standard fan-out
    to get the full payload. Yields the ``Table`` sub-object from each
    DescribeTable response so the manifest's ``items_path`` and
    ``natural_key`` see a flat dict with ``TableArn`` at the root.

    Regional: the engine binds ``client_for`` to the current region; this
    function runs once per region in the run's scope.
    """
    client = client_for("dynamodb")
    for page in _pages(client, "list_tables"):
        for name in page.get("TableNames", []):
            try:
                desc = without_response_metadata(client.describe_table(TableName=name))
            except (BotoCoreError, ClientError):
                # Per-table failures are skipped silently here; the engine's
                # per-entry error path (ENTRY_SKIPPED) is too coarse for a
                # per-item miss. The run's RGTA sweep would still cover tags
                # for any table we missed, and other passes can fill the gap.
                continue
            table = desc.get("Table") or {}
            if table:
                yield table


def iam_oidc_providers_described(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Enumerate IAM OIDC identity providers (global) and describe each.

    ``ListOpenIDConnectProviders`` returns ARNs only; ``GetOpenIDConnectProvider``
    is the per-ARN fan-out for URL, client IDs, thumbprints, and inline tags.
    Each yielded item embeds the source ARN as ``ProviderArn`` so the manifest
    entry can use it as ``natural_key`` (the GetOpenIDConnectProvider response
    doesn't echo the ARN back).

    IAM is global; the engine binds a us-east-1 client for global entries.
    """
    client = session.client("iam", region_name="us-east-1")
    listing = without_response_metadata(client.list_open_id_connect_providers())
    for entry in listing.get("OpenIDConnectProviderList", []):
        arn = entry.get("Arn")
        if not arn:
            continue
        try:
            details = without_response_metadata(
                client.get_open_id_connect_provider(OpenIDConnectProviderArn=arn)
            )
        except (BotoCoreError, ClientError):
            continue
        yield {**details, "ProviderArn": arn}


# Manifest custom_fn name -> callable.
_CUSTOM_FNS = {
    "s3_buckets_hydrated": s3_buckets_hydrated,
    "route53_zones_with_alias_targets": route53_zones_with_alias_targets,
    "dynamodb_tables_described": dynamodb_tables_described,
    "iam_oidc_providers_described": iam_oidc_providers_described,
}


def build_custom_fn_registry() -> CustomFnRegistry:
    """The populated ``custom_fn`` registry for the collector.

    Both v0 ``custom_fn`` seams are registered: S3's hydrate fan-out and
    Route 53's CloudFront-alias cross-join. An unregistered ``custom_fn``
    still classifies-and-skips, so the registry stays the single source.
    """
    registry = CustomFnRegistry()
    for name, fn in _CUSTOM_FNS.items():
        registry.register(name, fn)
    return registry
