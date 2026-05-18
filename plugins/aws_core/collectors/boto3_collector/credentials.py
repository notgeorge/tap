"""AWS credential / session / region resolution for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-secrets.md
(req-aws-core-secret-aws-static) and
plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-credentials / req-aws-collector-regions).

``aws_core`` owns the ``aws_static_access_key`` ``data`` shape and validates
it consumer-side; ``tap_cares`` owns only the secrets *mechanics*
(``req-tap-cares-secrets-consumer-kinds``). Region scope is operator-owned and
carried on the secret: a non-empty ``data.regions_allowed`` scopes regional
collection to exactly those regions; absent, the singular ``data.region`` is the sole
region; with neither, the run fails visibly.

The collector never reads credential files directly — credentials resolve
through the ``tap_cares`` secrets subsystem.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import boto3
from botocore.config import Config

from tap_cares.secrets import SecretRef, require_secret_kind, resolve_secret
from tap_cares.secrets.models import Secret

# The well-known SecretRef for the AWS collector. v0 has no per-instance
# config (CollectorConfig carries only entity ids), so the key is a constant;
# the operator drops ``aws/boto_collector.secret.json`` under TAP_SECRETS_ROOT
# (no plugin config in core infra — operator-owned, off-grid).
AWS_SECRET_REF = SecretRef(scope="aws", key="boto_collector")
AWS_SECRET_KIND = "aws_static_access_key"

# aws_core owns this schema for the kind's `data` (req-aws-core-secret-aws-static-2).
# Strict: `data` is exactly credentials + region scope; operator metadata
# belongs in the secret's separate `metadata`, not here.
AWS_STATIC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["access_key_id", "secret_access_key"],
    "properties": {
        "access_key_id": {"type": "string", "minLength": 1},
        "secret_access_key": {"type": "string", "minLength": 1},
        "session_token": {"type": "string", "minLength": 1},
        "region": {"type": "string", "minLength": 1},
        "regions_allowed": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
}


class CredentialError(Exception):
    """The AWS secret is missing region scope or is otherwise unusable."""


def resolve_aws_secret(ref: SecretRef = AWS_SECRET_REF) -> Secret:
    """Resolve and validate the AWS collector secret.

    Raises ``SecretNotFoundError`` (missing) or ``SecretValidationError``
    (wrong kind / bad ``data`` shape) from the secrets subsystem.
    """
    secret = resolve_secret(ref)
    require_secret_kind(secret, AWS_SECRET_KIND, data_schema=AWS_STATIC_SCHEMA)
    return secret


def resolve_regions(data: Mapping[str, Any]) -> list[str]:
    """Regions to sweep: ``data.regions_allowed`` if non-empty, else ``[region]``.

    Raises ``CredentialError`` if the secret defines neither.
    """
    regions = data.get("regions_allowed")
    if regions:
        return list(regions)
    region = data.get("region")
    if region:
        return [region]
    raise CredentialError(
        "AWS secret defines no region: set data.regions_allowed (list) "
        "or data.region"
    )


def build_session(data: Mapping[str, Any]) -> boto3.session.Session:
    """A boto3 Session bound to the secret's static credentials."""
    return boto3.session.Session(
        aws_access_key_id=data["access_key_id"],
        aws_secret_access_key=data["secret_access_key"],
        aws_session_token=data.get("session_token"),
    )


def client_factory(
    session: boto3.session.Session, region: str
) -> Callable[[str], Any]:
    """A ``client_for(service)`` bound to ``region`` (for ``iter_source``)."""

    def client_for(service: str) -> Any:
        return session.client(service, region_name=region)

    return client_for


def caller_account_id(
    session: boto3.session.Session, region: str, *, timeout_seconds: int
) -> str:
    """The AWS account id via STS ``GetCallerIdentity``.

    A cheap read-only reachability probe requiring no resource permissions
    (also the self-test live check). Bounded by ``timeout_seconds``.
    """
    sts = session.client(
        "sts",
        region_name=region,
        config=Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries={"max_attempts": 1},
        ),
    )
    return str(sts.get_caller_identity()["Account"])
