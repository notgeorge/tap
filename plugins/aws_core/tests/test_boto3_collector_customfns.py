"""Unit tests for registered custom_fns (boto3-free, no DB).

Covers req-aws-collector-source: the route53_zones_with_alias_targets
cross-join — list CloudFront once, build domain->ARN, enrich each zone
with resolved alias_cloudfront_arns so ROUTES_TRAFFIC resolves by ARN
identity with no transform. Filters non-CloudFront aliases; keeps raw
domains lossless; resolves nothing it can't map (no bogus ARN).

Also covers aws_account_singleton (synthesizes the one aws_account node
from STS GetCallerIdentity + optional IAM account alias) and
cloudfront_distributions_with_oac (resolves and embeds each origin's
Origin Access Control config in the distribution's configuration).
"""

from __future__ import annotations

from botocore.exceptions import ClientError

from plugins.aws_core.collectors.boto3_collector.customfns import (
    aws_account_singleton,
    cloudfront_distributions_with_oac,
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

    def test_ipv4_ipv6_alias_pair_dedupes(self):
        # Regression (found live): the standard CloudFront setup has BOTH
        # an A and an AAAA alias to the same distribution. Without dedup
        # the domain/ARN appears twice -> two edges with the same
        # deterministic edge_entity_id -> GRIFT rejects the whole batch
        # (duplicate_entity_id). One distribution -> one resolved ARN.
        rrs = [
            {
                "Name": "samsite.unified-systems.com.",
                "Type": "A",
                "AliasTarget": {"DNSName": f"{_CF_DOMAIN}."},
            },
            {
                "Name": "samsite.unified-systems.com.",
                "Type": "AAAA",
                "AliasTarget": {"DNSName": f"{_CF_DOMAIN}."},
            },
        ]
        z = next(iter(route53_zones_with_alias_targets(_FakeSession(rrs))))
        assert z["alias_cloudfront_domains"] == [_CF_DOMAIN]
        assert z["alias_cloudfront_arns"] == [_CF_ARN]


# ---------------------------------------------------------------------------
# aws_account_singleton — synthesize the one aws_account node
# ---------------------------------------------------------------------------


class _FakeSts:
    def get_caller_identity(self, **_kw):
        return {
            "Account": "180731181784",
            "Arn": "arn:aws:iam::180731181784:user/collector",
            "UserId": "AIDAEXAMPLE",
            "ResponseMetadata": {"RequestId": "strip-me"},
        }


class _FakeIam:
    def __init__(self, aliases=None, raise_error=False):
        self._aliases = aliases or []
        self._raise = raise_error

    def list_account_aliases(self, **_kw):
        if self._raise:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "ListAccountAliases",
            )
        return {"AccountAliases": self._aliases, "ResponseMetadata": {"RequestId": "x"}}


class _FakeAccountSession:
    def __init__(self, aliases=None, iam_raises=False):
        self._aliases = aliases
        self._iam_raises = iam_raises

    def client(self, service: str, **_kw):
        if service == "sts":
            return _FakeSts()
        if service == "iam":
            return _FakeIam(self._aliases, self._iam_raises)
        raise AssertionError(f"unexpected client {service!r}")


class TestAwsAccountSingleton:
    def test_yields_exactly_one_item_keyed_by_account(self):
        items = list(aws_account_singleton(_FakeAccountSession(aliases=["sbtf-tech"])))
        assert len(items) == 1
        # Account id is at "Account" — the manifest natural_key.
        assert items[0]["Account"] == "180731181784"
        # ResponseMetadata stripped.
        assert "ResponseMetadata" not in items[0]

    def test_alias_becomes_the_name(self):
        item = next(iter(aws_account_singleton(_FakeAccountSession(aliases=["sbtf-tech"]))))
        assert item["_account_name"] == "sbtf-tech"
        assert item["_account_aliases"] == ["sbtf-tech"]

    def test_name_falls_back_to_id_form_when_no_alias(self):
        item = next(iter(aws_account_singleton(_FakeAccountSession(aliases=[]))))
        assert item["_account_name"] == "AWS Account 180731181784"

    def test_iam_failure_is_non_fatal_name_falls_back(self):
        # A denied/failed ListAccountAliases must not fail the account node —
        # the name just falls back to the id form.
        item = next(iter(aws_account_singleton(_FakeAccountSession(iam_raises=True))))
        assert item["_account_name"] == "AWS Account 180731181784"
        assert item["_account_aliases"] == []


# ---------------------------------------------------------------------------
# cloudfront_distributions_with_oac — embed each origin's OAC config
# ---------------------------------------------------------------------------

_OAC = {
    "Id": "EG8DXNRAHC015",
    "OriginAccessControlConfig": {
        "Name": "samsite-oac",
        "SigningProtocol": "sigv4",
        "SigningBehavior": "always",
        "OriginAccessControlOriginType": "s3",
    },
}


class _FakeCloudFrontOac:
    def __init__(self, distributions):
        self._distributions = distributions
        self.oac_calls: list[str] = []

    def can_paginate(self, _m: str) -> bool:
        return False

    def list_distributions(self, **_kw):
        return {
            "DistributionList": {"Items": self._distributions},
            "ResponseMetadata": {"RequestId": "strip-me"},
        }

    def get_origin_access_control(self, *, Id, **_kw):  # noqa: N803 — boto3 kwarg name
        self.oac_calls.append(Id)
        return {"OriginAccessControl": _OAC, "ResponseMetadata": {"RequestId": "x"}}


class _FakeOacSession:
    def __init__(self, distributions):
        self.cf = _FakeCloudFrontOac(distributions)

    def client(self, service: str, **_kw):
        if service == "cloudfront":
            return self.cf
        raise AssertionError(f"unexpected client {service!r}")


class TestCloudfrontDistributionsWithOac:
    def test_oac_resolved_and_embedded(self):
        dist = {
            "ARN": "arn:aws:cloudfront::111:distribution/E1",
            "DomainName": "d1.cloudfront.net",
            "Origins": {"Items": [{"Id": "s3-origin", "OriginAccessControlId": "EG8DXNRAHC015"}]},
        }
        items = list(cloudfront_distributions_with_oac(_FakeOacSession([dist])))
        assert len(items) == 1
        oacs = items[0]["_origin_access_controls"]
        assert set(oacs.keys()) == {"EG8DXNRAHC015"}
        cfg = oacs["EG8DXNRAHC015"]["OriginAccessControlConfig"]
        assert cfg["SigningProtocol"] == "sigv4"
        # Distribution identity/projection fields preserved verbatim.
        assert items[0]["ARN"] == "arn:aws:cloudfront::111:distribution/E1"

    def test_distribution_with_no_oac_yields_empty_map(self):
        dist = {
            "ARN": "arn:aws:cloudfront::111:distribution/E2",
            "DomainName": "d2.cloudfront.net",
            "Origins": {"Items": [{"Id": "custom-origin", "OriginAccessControlId": ""}]},
        }
        item = next(iter(cloudfront_distributions_with_oac(_FakeOacSession([dist]))))
        assert item["_origin_access_controls"] == {}

    def test_shared_oac_resolved_once(self):
        # Two distributions referencing the same OAC -> one GetOriginAccessControl
        # call (the oac_cache dedups across distributions).
        dists = [
            {
                "ARN": "arn:aws:cloudfront::111:distribution/E1",
                "Origins": {"Items": [{"OriginAccessControlId": "EG8DXNRAHC015"}]},
            },
            {
                "ARN": "arn:aws:cloudfront::111:distribution/E2",
                "Origins": {"Items": [{"OriginAccessControlId": "EG8DXNRAHC015"}]},
            },
        ]
        session = _FakeOacSession(dists)
        items = list(cloudfront_distributions_with_oac(session))
        assert len(items) == 2
        assert session.cf.oac_calls == ["EG8DXNRAHC015"]  # called exactly once
