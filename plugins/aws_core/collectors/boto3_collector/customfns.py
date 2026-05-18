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


def s3_buckets_hydrated(session: Any) -> Iterator[dict[str, Any]]:
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
        except (ClientError, BotoCoreError):
            region = "us-east-1"
        regional = session.client("s3", region_name=region)
        yield hydrate_item(
            regional, bucket, hydrate_ops, call_kwargs={"Bucket": name}
        )


# Manifest custom_fn name -> callable.
_CUSTOM_FNS = {
    "s3_buckets_hydrated": s3_buckets_hydrated,
}


def build_custom_fn_registry() -> CustomFnRegistry:
    """The populated ``custom_fn`` registry for the collector.

    Route 53's ``route53_zones_with_alias_targets`` is registered with the
    coupled edge-identity work; an unregistered ``custom_fn`` still
    classifies-and-skips, so its absence here is safe.
    """
    registry = CustomFnRegistry()
    for name, fn in _CUSTOM_FNS.items():
        registry.register(name, fn)
    return registry
