"""Trusted Steampipe query profiles for AWS collection."""

from __future__ import annotations

from dataclasses import dataclass


class AwsSteampipeProfileError(ValueError):
    """Raised when a requested AWS Steampipe profile is unknown."""


@dataclass(frozen=True, slots=True)
class SteampipeQuery:
    name: str
    table: str
    sql: str


@dataclass(frozen=True, slots=True)
class CollectionProfile:
    key: str
    description: str
    queries: tuple[SteampipeQuery, ...]


VPC_SUBNET_V0 = CollectionProfile(
    key="vpc-subnet-v0",
    description="Collect VPC and subnet rows for the first AWS Steampipe collector slice.",
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

_PROFILES: dict[str, CollectionProfile] = {
    VPC_SUBNET_V0.key: VPC_SUBNET_V0,
}


def get_profile(key: str) -> CollectionProfile:
    try:
        return _PROFILES[key]
    except KeyError:
        available = ", ".join(sorted(_PROFILES))
        raise AwsSteampipeProfileError(
            f"Unknown AWS Steampipe collector profile {key!r}. Available: {available}."
        ) from None


def list_profiles() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))
