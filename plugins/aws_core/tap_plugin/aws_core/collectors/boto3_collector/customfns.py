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
        if entry["entity_type"] == "aws_core__aws_s3_bucket":
            ops: list[dict[str, str]] = entry.get("hydrate", [])
            return ops
    return []


def _resolve_bucket_region(base_client: Any, bucket_name: str) -> str:
    """Resolve a bucket's home region.

    ``GetBucket*`` calls are region-bound (S3 redirects otherwise);
    ``GetBucketLocation`` against the global endpoint gives the region.
    A failed lookup falls back to ``us-east-1``.
    """
    try:
        location = base_client.get_bucket_location(Bucket=bucket_name)
        return location.get("LocationConstraint") or "us-east-1"
    except (ClientError, BotoCoreError):
        return "us-east-1"


# BucketSizeBytes has no all-tiers rollup dimension — it must be queried per
# storage tier. NumberOfObjects has the convenient AllStorageTypes. The
# collector sums whichever size tiers return data, so a lifecycled bucket
# (objects tiered to Glacier etc.) reports a complete total.
_S3_SIZE_STORAGE_TYPES = (
    "StandardStorage",
    "IntelligentTieringFAStorage",
    "IntelligentTieringIAStorage",
    "StandardIAStorage",
    "OneZoneIAStorage",
    "GlacierInstantRetrievalStorage",
    "GlacierStorage",
    "DeepArchiveStorage",
    "ReducedRedundancyStorage",
)


def _bucket_size_metrics(cw_client: Any, bucket_name: str) -> dict[str, Any]:
    """Aggregate bucket size + object count from CloudWatch storage metrics.

    S3 publishes ``BucketSizeBytes`` / ``NumberOfObjects`` to the ``AWS/S3``
    CloudWatch namespace daily, free. One ``get_metric_data`` call per bucket
    batches the ``NumberOfObjects`` query and a ``BucketSizeBytes`` query per
    storage tier; tiers with data are summed. This is the fast path — the
    alternative (summing ``list_objects_v2``) is one call per 1000 objects.

    ``size_observed_at`` is the datapoint's own ``Timestamp`` — the
    data-currency disclosure (the metrics are daily, so the values are not
    real-time; the consumer derives staleness from this timestamp). See
    req-aws-collector-s3-bucket-size.

    A denied/failed CloudWatch call is non-fatal: the three fields come back
    empty/null (unknown, never a misleading 0) and the bucket still collects.
    """
    from datetime import UTC, datetime, timedelta

    empty: dict[str, Any] = {"size_bytes": None, "object_count": None, "size_observed_at": ""}
    end = datetime.now(UTC)
    start = end - timedelta(days=3)  # daily metric — a 3-day window catches the latest

    def _query(qid: str, metric: str, storage_type: str) -> dict[str, Any]:
        return {
            "Id": qid,
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/S3",
                    "MetricName": metric,
                    "Dimensions": [
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": storage_type},
                    ],
                },
                "Period": 86400,
                "Stat": "Average",
            },
            "ReturnData": True,
        }

    queries = [_query("objcount", "NumberOfObjects", "AllStorageTypes")]
    queries += [_query(f"size{i}", "BucketSizeBytes", st) for i, st in enumerate(_S3_SIZE_STORAGE_TYPES)]

    try:
        resp = cw_client.get_metric_data(
            MetricDataQueries=queries,
            StartTime=start,
            EndTime=end,
            ScanBy="TimestampDescending",
        )
    except (BotoCoreError, ClientError):
        return dict(empty)

    object_count: int | None = None
    size_bytes: int | None = None
    latest: Any = None
    for result in resp.get("MetricDataResults", []):
        values = result.get("Values") or []
        if not values:
            continue
        timestamps = result.get("Timestamps") or []
        # ScanBy=TimestampDescending -> index 0 is the most recent datapoint.
        value = values[0]
        ts = timestamps[0] if timestamps else None
        if ts is not None and (latest is None or ts > latest):
            latest = ts
        if result.get("Id") == "objcount":
            object_count = int(value)
        else:
            size_bytes = (size_bytes or 0) + int(value)

    if object_count is None and size_bytes is None:
        return dict(empty)
    return {
        "size_bytes": size_bytes,
        "object_count": object_count,
        "size_observed_at": latest.isoformat() if latest is not None else "",
    }


def s3_buckets_hydrated(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Enumerate S3 buckets and fan out each bucket's compliance sub-config.

    Yields one envelope per bucket: the ``ListBuckets`` item at the root
    (carrying ``BucketArn`` — the stable natural key), the ``_hydrate`` /
    ``_hydrate_mapping`` siblings the hydrate template assembles, and the
    aggregate ``size_bytes`` / ``object_count`` / ``size_observed_at`` from
    CloudWatch storage metrics (req-aws-collector-s3-bucket-size).
    """
    base = session.client("s3")
    listing = without_response_metadata(base.list_buckets())
    hydrate_ops = _s3_hydrate_ops()

    for bucket in listing.get("Buckets", []):
        name = bucket.get("Name")
        region = _resolve_bucket_region(base, name)
        regional = session.client("s3", region_name=region)
        envelope = hydrate_item(regional, bucket, hydrate_ops, call_kwargs={"Bucket": name})
        # CloudWatch S3 storage metrics are region-bound, like GetBucket*.
        cw = session.client("cloudwatch", region_name=region)
        envelope.update(_bucket_size_metrics(cw, name))
        yield envelope


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


def aws_account_singleton(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Synthesize the one ``aws_account`` node for the account this run scopes to.

    No AWS API enumerates "the account" as a resource — ``STS
    GetCallerIdentity`` is the canonical way to learn which account the
    run's credentials belong to. The optional IAM account alias
    (``ListAccountAliases``) supplies a friendlier name; absent an alias the
    name falls back to ``AWS Account <id>``.

    Yields exactly one item. The account id sits at ``Account`` — the
    manifest entry's ``natural_key`` — so ``node_entity_id("aws_account",
    "<id>")`` is deterministic. Any node minted elsewhere with the same id
    (e.g. a hand-written GRIFT batch) upserts cleanly onto the collector's.

    STS and IAM are global; clients are bound to ``us-east-1`` per the
    global-resource region invariant.
    """
    sts = session.client("sts", region_name="us-east-1")
    identity = without_response_metadata(sts.get_caller_identity())
    account_id = identity.get("Account") or ""

    aliases: list[str] = []
    try:
        iam = session.client("iam", region_name="us-east-1")
        alias_resp = without_response_metadata(iam.list_account_aliases())
        aliases = list(alias_resp.get("AccountAliases", []) or [])
    except (BotoCoreError, ClientError):
        # The account alias is a nicety, not load-bearing — a denied or
        # failed ListAccountAliases just falls the name back to the id form.
        aliases = []

    yield {
        "Account": account_id,
        "Arn": identity.get("Arn"),
        "UserId": identity.get("UserId"),
        "_account_name": aliases[0] if aliases else f"AWS Account {account_id}",
        "_account_aliases": aliases,
    }


def cloudfront_distributions_with_oac(session: Any, *, client_for: Any = None) -> Iterator[dict[str, Any]]:
    """Enumerate CloudFront distributions, embedding each origin's OAC config.

    ``ListDistributions`` returns distribution summaries that carry an
    ``Origins.Items[].OriginAccessControlId`` — but the OAC itself (its
    signing protocol/behavior and origin type) lives behind a separate
    ``GetOriginAccessControl`` call. An OAC has no ARN; it is referenced by
    an opaque ``Id``. This ``custom_fn`` resolves every distinct OAC id a
    distribution's origins reference and embeds the results under
    ``_origin_access_controls`` (an ``{oac_id: details}`` map) so they land
    losslessly in the distribution's ``configuration``. The OAC is a
    configuration detail of the distribution, not a separate node — the
    "have it handy" call from the strat-sam-demo discussion (2026-05-21).

    The yielded item is the unchanged ``DistributionSummary`` plus that one
    extra key, so the manifest's ``natural_key`` (``ARN``), ``fields``,
    ``tags``, and ``edges`` (``Origins.Items[].DomainName``,
    ``ViewerCertificate.ACMCertificateArn``) all still resolve.

    CloudFront is global; the client is bound to ``us-east-1`` per the
    global-resource region invariant.
    """
    cf = session.client("cloudfront", region_name="us-east-1")
    # Cache across distributions: two distributions sharing an OAC -> one call.
    oac_cache: dict[str, Any] = {}
    for page in _pages(cf, "list_distributions"):
        for dist in (page.get("DistributionList", {}) or {}).get("Items", []) or []:
            oac_ids: list[str] = []
            for origin in (dist.get("Origins") or {}).get("Items", []) or []:
                oac_id = origin.get("OriginAccessControlId")
                if oac_id and oac_id not in oac_ids:
                    oac_ids.append(oac_id)
            oacs: dict[str, Any] = {}
            for oac_id in oac_ids:
                if oac_id not in oac_cache:
                    try:
                        resp = without_response_metadata(
                            cf.get_origin_access_control(Id=oac_id)
                        )
                        oac_cache[oac_id] = resp.get("OriginAccessControl") or resp
                    except (BotoCoreError, ClientError):
                        # A per-OAC miss is non-fatal: the distribution still
                        # collects; the slot records None so the gap is visible.
                        oac_cache[oac_id] = None
                oacs[oac_id] = oac_cache[oac_id]
            yield {**dist, "_origin_access_controls": oacs}


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


def eventbridge_rules_with_targets(session: Any, *, client_for: Any) -> Iterator[dict[str, Any]]:
    """Enumerate EventBridge rules (regional) with their target ARNs resolved.

    ``ListRules`` returns the rule itself — name, schedule, state, RoleArn —
    but not *what it invokes*. A rule's targets live behind a separate
    ``ListTargetsByRule`` call. This custom_fn fans that call out per rule
    and attaches the target ARNs so the rule → target relationship resolves
    as an edge; without it a scheduled rule and the Lambda it triggers sit
    on the grid as disconnected nodes.

    Two keys are attached:

    - ``_target_arns`` — every target ARN, lossless (→ ``configuration``).
    - ``_lambda_target_arns`` — the Lambda-only subset, which the ``INVOKES``
      edge rule resolves against. EventBridge targets are polymorphic (SQS,
      SNS, Step Functions, ECS, …) and the v0 edge rule resolves a single
      ``target_type``; filtering to Lambda ARNs here keeps non-Lambda
      targets from producing dangling edges.

    Regional: the engine binds ``client_for`` to the current region. Rules
    are enumerated on the default event bus (parity with the prior
    ``ListRules`` source); custom event buses are future scope.
    """
    client = client_for("events")
    for page in _pages(client, "list_rules"):
        for rule in page.get("Rules", []):
            name = rule.get("Name")
            bus = rule.get("EventBusName") or "default"
            target_arns: list[str] = []
            try:
                for tpage in _pages(client, "list_targets_by_rule", Rule=name, EventBusName=bus):
                    for target in tpage.get("Targets", []):
                        arn = target.get("Arn")
                        if arn:
                            target_arns.append(arn)
            except (BotoCoreError, ClientError):
                # A per-rule ListTargetsByRule failure is non-fatal: the rule
                # still collects, just without resolved target edges.
                target_arns = []
            target_arns = list(dict.fromkeys(target_arns))
            lambda_arns = [
                a for a in target_arns if a.startswith("arn:aws:lambda:") and ":function:" in a
            ]
            yield {**rule, "_target_arns": target_arns, "_lambda_target_arns": lambda_arns}


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
    "aws_account_singleton": aws_account_singleton,
    "s3_buckets_hydrated": s3_buckets_hydrated,
    "route53_zones_with_alias_targets": route53_zones_with_alias_targets,
    "cloudfront_distributions_with_oac": cloudfront_distributions_with_oac,
    "dynamodb_tables_described": dynamodb_tables_described,
    "eventbridge_rules_with_targets": eventbridge_rules_with_targets,
    "iam_oidc_providers_described": iam_oidc_providers_described,
}


def build_custom_fn_registry() -> CustomFnRegistry:
    """The populated ``custom_fn`` registry for the collector.

    Every ``custom_fn`` named by the manifest is registered here — the
    registry is the single source. An unregistered ``custom_fn`` still
    classifies-and-skips rather than crashing the run.
    """
    registry = CustomFnRegistry()
    for name, fn in _CUSTOM_FNS.items():
        registry.register(name, fn)
    return registry
