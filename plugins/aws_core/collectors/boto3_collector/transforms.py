"""Edge value transforms + registry population for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-edges — derived edge keys).

An edge ``transform`` maps the raw extracted value to the *target's natural
key* so the edge resolves by deterministic identity with no cross-resource
lookup. Transforms are pure (value in, key out) and registered here — code is
never loaded from manifest data (``req-aws-collector-source-3``).

A transform returns ``None`` when the value is not a valid target of this
edge (e.g. a CloudFront origin that is not an S3 bucket); the edge pass drops
``None`` so no bogus edge is fabricated.
"""

from __future__ import annotations

import re

from .edges import TransformRegistry

# CloudFront S3 origin DomainName forms, all ending amazonaws.com:
#   bucket.s3.amazonaws.com
#   bucket.s3.us-east-1.amazonaws.com
#   bucket.s3-us-east-1.amazonaws.com
#   bucket.s3-website-us-east-1.amazonaws.com
#   bucket.s3-website.us-east-1.amazonaws.com
# The bucket is everything before the first ``.s3`` segment. A non-S3 origin
# (ALB, API Gateway, custom) does not match -> None (no edge).
_S3_ORIGIN_RE = re.compile(
    r"^(?P<bucket>[^/]+?)\.s3(?:[.-][a-z0-9-]+)*\.amazonaws\.com$",
    re.IGNORECASE,
)


def s3_bucket_name_from_origin_domain(value: object) -> str | None:
    """A CloudFront origin DomainName -> the target S3 bucket's natural key.

    The S3 bucket natural key is its ARN, which is globally derivable from
    the name alone (``arn:aws:s3:::<bucket>`` — no account/region), so this
    stays a pure transform and the edge resolves by identity.
    """
    if not isinstance(value, str):
        return None
    match = _S3_ORIGIN_RE.match(value.strip())
    if not match:
        return None
    return f"arn:aws:s3:::{match.group('bucket')}"


# Manifest transform name -> callable. The single source of truth wired into
# the engine's TransformRegistry by build_transform_registry().
_TRANSFORMS = {
    "s3_bucket_name_from_origin_domain": s3_bucket_name_from_origin_domain,
}


def build_transform_registry() -> TransformRegistry:
    """The populated edge-transform registry for the collector."""
    registry = TransformRegistry()
    for name, fn in _TRANSFORMS.items():
        registry.register(name, fn)
    return registry
