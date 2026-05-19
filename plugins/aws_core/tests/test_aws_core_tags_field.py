"""The canonical `tags` field on the collected aws_core models.

Covers req-aws-core-fields-4 (v0 scope: the 8 manifest-collected models).
Uniform name + shape + default so cross-resource tag queries work by
convention; declared in both schemas; never an Entity-spine facet.
"""

from __future__ import annotations

import pytest

from plugins.aws_core.models.acm_certificate import AcmCertificate
from plugins.aws_core.models.cloudfront_distribution import CloudfrontDistribution
from plugins.aws_core.models.cloudwatch_log_group import CloudwatchLogGroup
from plugins.aws_core.models.eventbridge_rule import EventbridgeRule
from plugins.aws_core.models.iam_role import IamRole
from plugins.aws_core.models.lambda_function import LambdaFunction
from plugins.aws_core.models.route53_hosted_zone import Route53HostedZone
from plugins.aws_core.models.s3_bucket import S3Bucket

_COLLECTED_MODELS = [
    AcmCertificate,
    CloudfrontDistribution,
    CloudwatchLogGroup,
    EventbridgeRule,
    IamRole,
    LambdaFunction,
    Route53HostedZone,
    S3Bucket,
]


@pytest.mark.parametrize("model", _COLLECTED_MODELS, ids=lambda m: m.ENTITY_TYPE)
class TestCanonicalTagsField:
    def test_field_exists_defaults_empty_dict(self, model):
        field = model._meta.get_field("tags")
        assert field.get_internal_type() == "JSONField"
        assert field.default is dict  # uniform empty-map default
        assert field.blank is True

    def test_declared_in_both_schemas(self, model):
        assert model.FIELD_CRUD_SCHEMA["tags"] == {"type": "object"}
        assert model.FIELD_VALIDATION_SCHEMA["tags"] == {
            "validation": "jsonschema",
            "schema": {"type": "object"},
        }

    def test_uniform_name_across_family(self, model):
        # The query-by-convention contract: same attribute name everywhere.
        assert hasattr(model, "tags")
