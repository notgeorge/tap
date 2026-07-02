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

from tap_plugin.aws_core.collectors.boto3_collector.customfns import (
    _bucket_size_metrics,
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


# ---------------------------------------------------------------------------
# _bucket_size_metrics — aggregate bucket size + object count from CloudWatch
# ---------------------------------------------------------------------------

from datetime import UTC, datetime  # noqa: E402

_TS_OLD = datetime(2026, 5, 19, tzinfo=UTC)
_TS_NEW = datetime(2026, 5, 20, tzinfo=UTC)


class _FakeCloudWatch:
    """Fake CloudWatch — returns the canned MetricDataResults for get_metric_data."""

    def __init__(self, results=None, raise_error=False):
        self._results = results if results is not None else []
        self._raise = raise_error
        self.last_queries = None

    def get_metric_data(self, *, MetricDataQueries, StartTime, EndTime, ScanBy=None):  # noqa: N803
        self.last_queries = MetricDataQueries
        if self._raise:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "GetMetricData",
            )
        return {"MetricDataResults": self._results}


class TestBucketSizeMetrics:
    def test_object_count_and_single_tier_size(self):
        cw = _FakeCloudWatch(
            results=[
                {"Id": "objcount", "Values": [930.0], "Timestamps": [_TS_NEW]},
                {"Id": "size0", "Values": [1.0e8], "Timestamps": [_TS_NEW]},
            ]
        )
        m = _bucket_size_metrics(cw, "samsite-prod-1")
        assert m["object_count"] == 930
        assert m["size_bytes"] == 100_000_000
        assert m["size_observed_at"] == _TS_NEW.isoformat()

    def test_size_summed_across_storage_tiers(self):
        # A lifecycled bucket: Standard + Glacier tiers both report size.
        cw = _FakeCloudWatch(
            results=[
                {"Id": "objcount", "Values": [100.0], "Timestamps": [_TS_NEW]},
                {"Id": "size0", "Values": [1.0e9], "Timestamps": [_TS_NEW]},
                {"Id": "size6", "Values": [5.0e8], "Timestamps": [_TS_NEW]},
            ]
        )
        m = _bucket_size_metrics(cw, "lifecycled-bucket")
        assert m["size_bytes"] == 1_500_000_000  # both tiers summed
        assert m["object_count"] == 100

    def test_latest_timestamp_wins(self):
        # Datapoints from different days -> size_observed_at is the newest.
        cw = _FakeCloudWatch(
            results=[
                {"Id": "objcount", "Values": [5.0], "Timestamps": [_TS_OLD]},
                {"Id": "size0", "Values": [1.0e6], "Timestamps": [_TS_NEW]},
            ]
        )
        m = _bucket_size_metrics(cw, "b")
        assert m["size_observed_at"] == _TS_NEW.isoformat()

    def test_no_datapoints_is_unknown_not_zero(self):
        # A new/empty bucket with no CloudWatch data -> null fields, not 0.
        cw = _FakeCloudWatch(
            results=[
                {"Id": "objcount", "Values": [], "Timestamps": []},
                {"Id": "size0", "Values": [], "Timestamps": []},
            ]
        )
        m = _bucket_size_metrics(cw, "empty-bucket")
        assert m == {"size_bytes": None, "object_count": None, "size_observed_at": ""}

    def test_cloudwatch_failure_is_non_fatal(self):
        # A denied GetMetricData must not fail the bucket — empty/null result.
        cw = _FakeCloudWatch(raise_error=True)
        m = _bucket_size_metrics(cw, "b")
        assert m == {"size_bytes": None, "object_count": None, "size_observed_at": ""}

    def test_queries_cover_objects_and_every_size_tier(self):
        cw = _FakeCloudWatch(results=[])
        _bucket_size_metrics(cw, "b")
        ids = {q["Id"] for q in cw.last_queries}
        # One NumberOfObjects query + one BucketSizeBytes query per storage tier.
        assert "objcount" in ids
        assert sum(1 for i in ids if i.startswith("size")) >= 5


# ---------------------------------------------------------------------------
# eventbridge_rules_with_targets — resolve each rule's target ARNs
# ---------------------------------------------------------------------------

from tap_plugin.aws_core.collectors.boto3_collector.customfns import (  # noqa: E402
    eventbridge_rules_with_targets,
)

_LAMBDA_ARN = "arn:aws:lambda:us-east-2:180731181784:function:samsite-prod-1-opa-compliance"
_SQS_ARN = "arn:aws:sqs:us-east-2:180731181784:some-queue"


class _FakeEvents:
    def __init__(self, rules, targets_by_rule, targets_raise=False):
        self._rules = rules
        self._targets = targets_by_rule
        self._targets_raise = targets_raise

    def can_paginate(self, _m: str) -> bool:
        return False

    def list_rules(self, **_kw):
        return {"Rules": self._rules}

    def list_targets_by_rule(self, *, Rule, EventBusName, **_kw):  # noqa: N803
        if self._targets_raise:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "ListTargetsByRule",
            )
        return {"Targets": self._targets.get(Rule, [])}


def _events_client_for(fake_events):
    def _cf(service: str):
        assert service == "events"
        return fake_events

    return _cf


class TestEventbridgeRulesWithTargets:
    def test_lambda_target_resolved(self):
        rule = {
            "Name": "samsite-prod-1-opa-compliance",
            "Arn": "arn:aws:events:us-east-2:180731181784:rule/samsite-prod-1-opa-compliance",
            "State": "ENABLED",
            "ScheduleExpression": "rate(1 day)",
            "EventBusName": "default",
        }
        events = _FakeEvents([rule], {"samsite-prod-1-opa-compliance": [{"Id": "t1", "Arn": _LAMBDA_ARN}]})
        items = list(eventbridge_rules_with_targets(None, client_for=_events_client_for(events)))
        assert len(items) == 1
        item = items[0]
        # Rule identity/projection fields preserved verbatim.
        assert item["Name"] == "samsite-prod-1-opa-compliance"
        assert item["ScheduleExpression"] == "rate(1 day)"
        # The Lambda target resolves into the edge-bearing key.
        assert item["_target_arns"] == [_LAMBDA_ARN]
        assert item["_lambda_target_arns"] == [_LAMBDA_ARN]

    def test_non_lambda_target_kept_lossless_but_not_edge_bearing(self):
        # An SQS target stays in _target_arns (lossless -> configuration) but
        # is filtered out of _lambda_target_arns so it produces no dangling
        # INVOKES edge to a non-existent aws_lambda node.
        rule = {"Name": "r", "Arn": "arn:aws:events:us-east-2:1:rule/r", "EventBusName": "default"}
        events = _FakeEvents([rule], {"r": [{"Id": "t1", "Arn": _SQS_ARN}]})
        item = next(iter(eventbridge_rules_with_targets(None, client_for=_events_client_for(events))))
        assert item["_target_arns"] == [_SQS_ARN]
        assert item["_lambda_target_arns"] == []

    def test_mixed_targets_split(self):
        rule = {"Name": "r", "Arn": "arn:aws:events:us-east-2:1:rule/r", "EventBusName": "default"}
        events = _FakeEvents(
            [rule],
            {"r": [{"Id": "t1", "Arn": _LAMBDA_ARN}, {"Id": "t2", "Arn": _SQS_ARN}]},
        )
        item = next(iter(eventbridge_rules_with_targets(None, client_for=_events_client_for(events))))
        assert set(item["_target_arns"]) == {_LAMBDA_ARN, _SQS_ARN}
        assert item["_lambda_target_arns"] == [_LAMBDA_ARN]

    def test_list_targets_failure_is_non_fatal(self):
        # A denied ListTargetsByRule must not fail the rule — it still
        # collects, just with no resolved targets.
        rule = {"Name": "r", "Arn": "arn:aws:events:us-east-2:1:rule/r", "EventBusName": "default"}
        events = _FakeEvents([rule], {}, targets_raise=True)
        item = next(iter(eventbridge_rules_with_targets(None, client_for=_events_client_for(events))))
        assert item["Name"] == "r"
        assert item["_target_arns"] == []
        assert item["_lambda_target_arns"] == []
