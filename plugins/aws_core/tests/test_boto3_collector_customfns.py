"""Unit tests for registered custom_fns (boto3-free, no DB).

Covers req-aws-collector-source: the route53_zones_with_alias_targets
cross-join — list CloudFront once, build domain->ARN, enrich each zone
with resolved alias_cloudfront_arns so ROUTES_TRAFFIC resolves by ARN
identity with no transform. Filters non-CloudFront aliases; keeps raw
domains lossless; resolves nothing it can't map (no bogus ARN).
"""

from __future__ import annotations

from plugins.aws_core.collectors.boto3_collector.customfns import (
    route53_zones_with_alias_targets,
)

_CF_ARN = "arn:aws:cloudfront::111122223333:distribution/E1ABCDEF"
_CF_DOMAIN = "d111abcdef.cloudfront.net"


class _FakeCloudFront:
    def can_paginate(self, _m: str) -> bool:
        return False

    def list_distributions(self, **_kw):
        return {
            "DistributionList": {"Items": [{"ARN": _CF_ARN, "DomainName": _CF_DOMAIN}]},
            "ResponseMetadata": {"RequestId": "strip-me"},
        }


class _FakeRoute53:
    def __init__(self, record_sets):
        self._rrs = record_sets

    def can_paginate(self, _m: str) -> bool:
        return False

    def list_hosted_zones(self, **_kw):
        return {
            "HostedZones": [
                {
                    "Id": "/hostedzone/Z1SAMSITE",
                    "Name": "samsite.unified-systems.com.",
                    "Config": {"PrivateZone": False},
                    "ResourceRecordSetCount": 4,
                }
            ]
        }

    def list_resource_record_sets(self, **_kw):
        return {"ResourceRecordSets": self._rrs}


class _FakeSession:
    def __init__(self, record_sets):
        self._rrs = record_sets

    def client(self, service: str, **_kw):
        if service == "cloudfront":
            return _FakeCloudFront()
        if service == "route53":
            return _FakeRoute53(self._rrs)
        raise AssertionError(f"unexpected client {service!r}")


class TestRoute53ZonesWithAliasTargets:
    def test_cloudfront_alias_resolved_to_arn_others_filtered(self):
        rrs = [
            # A-alias to the CloudFront distribution (Route 53 trailing dot,
            # mixed case) -> resolved to the CF ARN.
            {
                "Name": "samsite.unified-systems.com.",
                "Type": "A",
                "AliasTarget": {"DNSName": f"{_CF_DOMAIN.upper()}."},
            },
            # Non-CloudFront alias (ELB) -> filtered out entirely.
            {
                "Name": "api.samsite.unified-systems.com.",
                "Type": "A",
                "AliasTarget": {"DNSName": "x.us-east-1.elb.amazonaws.com."},
            },
            # Plain record, no AliasTarget -> ignored.
            {
                "Name": "txt.samsite.unified-systems.com.",
                "Type": "TXT",
                "ResourceRecords": [{"Value": '"v=spf1"'}],
            },
        ]
        zones = list(route53_zones_with_alias_targets(_FakeSession(rrs)))

        assert len(zones) == 1
        z = zones[0]
        # Zone identity/projection fields preserved verbatim.
        assert z["Id"] == "/hostedzone/Z1SAMSITE"
        assert z["Name"] == "samsite.unified-systems.com."
        assert z["Config"] == {"PrivateZone": False}
        # Only the CloudFront alias survives; resolved to the ARN; raw
        # domain kept lossless (normalized: lowercased, dot-stripped).
        assert z["alias_cloudfront_domains"] == [_CF_DOMAIN]
        assert z["alias_cloudfront_arns"] == [_CF_ARN]

    def test_unmappable_cloudfront_domain_yields_no_arn(self):
        # A CloudFront alias whose distribution is not in the CF listing
        # (different account / not collected): the domain is captured, but
        # no bogus ARN is fabricated — arns stays empty.
        rrs = [
            {
                "Name": "samsite.unified-systems.com.",
                "Type": "A",
                "AliasTarget": {"DNSName": "dXXXXXXXXXXXXX.cloudfront.net."},
            }
        ]
        z = next(iter(route53_zones_with_alias_targets(_FakeSession(rrs))))
        assert z["alias_cloudfront_domains"] == ["dxxxxxxxxxxxxx.cloudfront.net"]
        assert z["alias_cloudfront_arns"] == []
