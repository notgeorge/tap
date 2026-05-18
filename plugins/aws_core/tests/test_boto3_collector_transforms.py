"""Unit tests for edge value transforms (boto3-free, no DB).

Covers req-aws-collector-edges (derived edge keys): the
s3_bucket_name_from_origin_domain transform yields the target S3 bucket's
natural key (its ARN) purely from a CloudFront origin DomainName, and
returns None for non-S3 origins so no bogus edge is fabricated.
"""

from __future__ import annotations

import pytest

from plugins.aws_core.collectors.boto3_collector.transforms import (
    build_custom_fn_registry,
    build_transform_registry,
    s3_bucket_name_from_origin_domain,
)


class TestS3BucketNameFromOriginDomain:
    @pytest.mark.parametrize(
        "domain",
        [
            "sam-site.s3.amazonaws.com",
            "sam-site.s3.us-east-2.amazonaws.com",
            "sam-site.s3-us-east-2.amazonaws.com",
            "sam-site.s3-website-us-east-2.amazonaws.com",
            "sam-site.s3-website.us-east-2.amazonaws.com",
        ],
    )
    def test_s3_origin_forms_yield_bucket_arn(self, domain):
        assert s3_bucket_name_from_origin_domain(domain) == "arn:aws:s3:::sam-site"

    def test_non_s3_origin_is_none(self):
        # ALB / API Gateway / custom origins are not S3 buckets -> no edge.
        assert s3_bucket_name_from_origin_domain("api.example.com") is None
        assert s3_bucket_name_from_origin_domain("lb-123.us-east-2.elb.amazonaws.com") is None

    def test_non_string_is_none(self):
        assert s3_bucket_name_from_origin_domain(None) is None
        assert s3_bucket_name_from_origin_domain(123) is None


class TestRegistryBuilders:
    def test_transform_registry_resolves_declared_transform(self):
        reg = build_transform_registry()
        fn = reg.get("s3_bucket_name_from_origin_domain")
        assert fn("sam-site.s3.amazonaws.com") == "arn:aws:s3:::sam-site"

    def test_custom_fn_registry_empty_until_route53_increment(self):
        # Empty is intentional; an unregistered custom_fn classifies-and-skips.
        assert build_custom_fn_registry()._fns == {}
