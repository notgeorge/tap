"""Hardcoded trusted Steampipe query set for AWS collection.

v0 collects VPC + subnet only. This is a hardcoded collector capability,
internally labelled ``vpc-subnet-v0`` — it is **not** operator-selectable
(the old "profile" knob is removed; see spec-aws-steampipe-collector-v0.md
`req-aws-steampipe-secret-discovery`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SteampipeQuery:
    name: str
    table: str
    sql: str


@dataclass(frozen=True, slots=True)
class CollectionProfile:
    """A trusted, hardcoded query set. Named for the internal scope label."""

    key: str
    description: str
    queries: tuple[SteampipeQuery, ...]


VPC_SUBNET_V0 = CollectionProfile(
    key="vpc-subnet-v0",
    description="Hardcoded v0 scope: collect VPC and subnet rows.",
    queries=(
        SteampipeQuery(
            name="vpcs",
            table="aws_vpc",
            sql="select * from aws_vpc;",
        ),
        SteampipeQuery(
            name="subnets",
            table="aws_vpc_subnet",
            sql="select * from aws_vpc_subnet;",
        ),
    ),
)

# Read-only single-row identity probe used by the self-test (no AWS SDK
# dependency — Steampipe is already the collection backend).
AWS_CALLER_IDENTITY_QUERY = SteampipeQuery(
    name="caller_identity",
    table="aws_caller_identity",
    sql="select account_id, arn from aws_caller_identity;",
)
