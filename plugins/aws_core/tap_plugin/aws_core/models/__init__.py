"""AWS Core plugin models package."""

from tap_plugin.aws_core.models.acm_certificate import AcmCertificate
from tap_plugin.aws_core.models.alb import Alb
from tap_plugin.aws_core.models.availability_zone import AvailabilityZone
from tap_plugin.aws_core.models.aws_account import AwsAccount
from tap_plugin.aws_core.models.aws_region import AwsRegion
from tap_plugin.aws_core.models.bedrock_model import BedrockModel
from tap_plugin.aws_core.models.cloudfront_distribution import CloudfrontDistribution
from tap_plugin.aws_core.models.cloudwatch_log_group import CloudwatchLogGroup
from tap_plugin.aws_core.models.dynamodb_table import DynamoDbTable
from tap_plugin.aws_core.models.ebs_volume import EbsVolume
from tap_plugin.aws_core.models.ec2_instance import Ec2Instance
from tap_plugin.aws_core.models.ecr_repository import EcrRepository
from tap_plugin.aws_core.models.ecs_cluster import EcsCluster
from tap_plugin.aws_core.models.ecs_service import EcsService
from tap_plugin.aws_core.models.ecs_task import EcsTask
from tap_plugin.aws_core.models.eks_cluster import EksCluster
from tap_plugin.aws_core.models.elastic_ip import ElasticIp
from tap_plugin.aws_core.models.elasticache_cluster import ElasticacheCluster
from tap_plugin.aws_core.models.elasticsearch_domain import ElasticsearchDomain
from tap_plugin.aws_core.models.elb import Elb
from tap_plugin.aws_core.models.eventbridge_rule import EventbridgeRule
from tap_plugin.aws_core.models.iam_oidc_provider import IamOidcProvider
from tap_plugin.aws_core.models.iam_policy import IamPolicy
from tap_plugin.aws_core.models.iam_role import IamRole
from tap_plugin.aws_core.models.iam_user import IamUser
from tap_plugin.aws_core.models.internet_gateway import InternetGateway
from tap_plugin.aws_core.models.lambda_function import LambdaFunction
from tap_plugin.aws_core.models.nat_gateway import NatGateway
from tap_plugin.aws_core.models.network_acl import NetworkAcl
from tap_plugin.aws_core.models.network_firewall import NetworkFirewall
from tap_plugin.aws_core.models.rds_instance import RdsInstance
from tap_plugin.aws_core.models.route53_hosted_zone import Route53HostedZone
from tap_plugin.aws_core.models.route_table import RouteTable
from tap_plugin.aws_core.models.s3_bucket import S3Bucket
from tap_plugin.aws_core.models.sagemaker_endpoint import SagemakerEndpoint
from tap_plugin.aws_core.models.secrets_manager_secret import SecretsManagerSecret
from tap_plugin.aws_core.models.security_group import SecurityGroup
from tap_plugin.aws_core.models.ssm_parameter import SsmParameter
from tap_plugin.aws_core.models.subnet import Subnet
from tap_plugin.aws_core.models.target_group import TargetGroup
from tap_plugin.aws_core.models.vpc import Vpc

__all__ = [
    "AcmCertificate",
    "Alb",
    "AvailabilityZone",
    "AwsAccount",
    "AwsRegion",
    "BedrockModel",
    "CloudfrontDistribution",
    "CloudwatchLogGroup",
    "DynamoDbTable",
    "EbsVolume",
    "Ec2Instance",
    "EcrRepository",
    "EcsCluster",
    "EcsService",
    "EcsTask",
    "EksCluster",
    "ElasticIp",
    "ElasticacheCluster",
    "ElasticsearchDomain",
    "Elb",
    "EventbridgeRule",
    "IamOidcProvider",
    "IamPolicy",
    "IamRole",
    "IamUser",
    "InternetGateway",
    "LambdaFunction",
    "NatGateway",
    "NetworkAcl",
    "NetworkFirewall",
    "RdsInstance",
    "Route53HostedZone",
    "RouteTable",
    "S3Bucket",
    "SagemakerEndpoint",
    "SecretsManagerSecret",
    "SecurityGroup",
    "SsmParameter",
    "Subnet",
    "TargetGroup",
    "Vpc",
]
