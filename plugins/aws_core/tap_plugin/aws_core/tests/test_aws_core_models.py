"""Domain-specific tests for AWS Core plugin models.

Model creation, edge connectivity, and structural validation are covered
by the centralized plugin validation system (test_aws_core_manifest.py).
These tests cover domain-specific behavior: field defaults, configuration
round-trips, and model-specific logic.
"""

import pytest
import tap_plugin.aws_core.models as aws  # noqa: F401 — trigger model registration

from tap_grid.models import Entity
from tap_grid.registry import get_model_class
from tap_grid.services import create_node


def _create(type_slug: str, payload: dict):
    """Create a node via the service layer and return the typed domain object."""
    result = create_node(type_slug, payload)
    assert result.success, f"create_node failed: {result.errors}"
    entity = Entity.objects.get(pk=result.entity_id)
    model_cls = get_model_class(type_slug)
    return model_cls.objects.get(entity=entity)


@pytest.mark.django_db
class TestAwsCoreDomainDefaults:
    """Test domain-specific default values."""

    def test_s3_bucket_public_access_blocked_defaults_true(self):
        node = _create("aws_core__aws_s3_bucket", {"name": "my-bucket"})
        assert node.public_access_blocked is True

    def test_ebs_volume_encrypted_defaults_false(self):
        node = _create("aws_core__aws_ebs_volume", {"volume_id": "vol-123"})
        assert node.encrypted is False

    def test_iam_user_mfa_defaults_false(self):
        node = _create("aws_core__aws_iam_user", {"name": "admin"})
        assert node.mfa_enabled is False

    def test_iam_policy_aws_managed_defaults_false(self):
        node = _create("aws_core__aws_iam_policy", {"name": "MyPolicy"})
        assert node.is_aws_managed is False


@pytest.mark.django_db
class TestAwsCoreConfigurationField:
    """Test that the configuration JSONField round-trips correctly."""

    def test_configuration_stores_nested_data(self):
        node = _create(
            "aws_core__aws_ec2_instance",
            {
                "instance_id": "i-config-test",
                "configuration": {
                    "tags": {"Name": "test", "env": "staging"},
                    "monitoring": True,
                    "security_groups": ["sg-1", "sg-2"],
                },
            },
        )
        assert node.configuration["tags"]["Name"] == "test"
        assert node.configuration["monitoring"] is True
        assert len(node.configuration["security_groups"]) == 2

    def test_configuration_defaults_to_empty_dict(self):
        node = _create("aws_core__aws_vpc", {"vpc_id": "vpc-empty-config"})
        assert node.configuration == {}
