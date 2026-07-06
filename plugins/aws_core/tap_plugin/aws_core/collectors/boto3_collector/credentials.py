"""AWS credential / session / region resolution for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-secrets.md
(req-aws-core-secret-aws-static / req-aws-core-secret-aws-assumed-role) and
plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-credentials / req-aws-collector-regions).

``aws_core`` owns the ``data`` shape of both AWS credential kinds and validates
them consumer-side; ``tap_cares`` owns only the secrets *mechanics*
(``req-tap-cares-secrets-consumer-kinds``). Two kinds are supported:

- ``aws_static_access_key`` — a session bound directly to static credentials
  (our own account).
- ``aws_assumed_role`` — cross-account: a *base* session (static credentials)
  calls STS ``AssumeRole`` with a **mandatory** External ID, and the returned
  short-lived credentials back the working session. This is how the collector
  reaches a running service in an AWS account we do not own.

Region scope is operator-owned and carried on the secret (identically for both
kinds): a non-empty ``data.regions_allowed`` scopes regional collection to
exactly those regions; absent, the singular ``data.region`` is the sole region;
with neither, the run fails visibly.

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
# the operator drops ``aws_core/boto_collector.secret.json`` under TAP_SECRETS_ROOT
# (no plugin config in core infra — operator-owned, off-grid). `scope` names the
# consuming plugin's slug, not the credential provider
# (req-tap-cares-secrets-consumer-scoping).
AWS_SECRET_REF = SecretRef(scope="aws_core", key="boto_collector")
AWS_SECRET_KIND = "aws_static_access_key"
AWS_ASSUMED_ROLE_KIND = "aws_assumed_role"

# Region scope is shared by both kinds; kept as one fragment so the two schemas
# cannot drift.
_REGION_SCOPE_PROPS: dict[str, Any] = {
    "region": {"type": "string", "minLength": 1},
    "regions_allowed": {
        "type": "array",
        "minItems": 1,
        "items": {"type": "string", "minLength": 1},
    },
}

# The static-credential fragment: reused verbatim as the `aws_assumed_role`
# kind's `data.base` (the identity that CALLS AssumeRole).
_STATIC_CREDS_PROPS: dict[str, Any] = {
    "access_key_id": {"type": "string", "minLength": 1},
    "secret_access_key": {"type": "string", "minLength": 1},
    "session_token": {"type": "string", "minLength": 1},
}

# aws_core owns this schema for the kind's `data` (req-aws-core-secret-aws-static-2).
# Strict: `data` is exactly credentials + region scope; operator metadata
# belongs in the secret's separate `metadata`, not here.
AWS_STATIC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["access_key_id", "secret_access_key"],
    "properties": {**_STATIC_CREDS_PROPS, **_REGION_SCOPE_PROPS},
}

# aws_core owns this schema for the cross-account kind's `data`
# (req-aws-core-secret-aws-assumed-role). `external_id` is REQUIRED — the target
# role's trust policy demands it, and we never call AssumeRole without the
# confused-deputy guard (req-aws-core-secret-aws-assumed-role-2).
AWS_ASSUMED_ROLE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["role_arn", "external_id", "base"],
    "properties": {
        "role_arn": {"type": "string", "minLength": 1},
        "external_id": {"type": "string", "minLength": 1},
        "base": {
            "type": "object",
            "additionalProperties": False,
            "required": ["access_key_id", "secret_access_key"],
            "properties": dict(_STATIC_CREDS_PROPS),
        },
        # 12-digit target account; enables the assert-on-land check.
        "expected_account_id": {"type": "string", "pattern": "^[0-9]{12}$"},
        # STS RoleSessionName grammar: [\w+=,.@-]{2,64}.
        "role_session_name": {
            "type": "string",
            "minLength": 2,
            "maxLength": 64,
            "pattern": r"^[\w+=,.@-]+$",
        },
        # AssumeRole DurationSeconds bounds (15 min .. 12 h).
        "duration_seconds": {"type": "integer", "minimum": 900, "maximum": 43200},
        **_REGION_SCOPE_PROPS,
    },
}

# Kind → consumer-owned `data` schema. The one place the collector enumerates
# which AWS credential kinds it accepts.
_KIND_SCHEMAS: dict[str, dict[str, Any]] = {
    AWS_SECRET_KIND: AWS_STATIC_SCHEMA,
    AWS_ASSUMED_ROLE_KIND: AWS_ASSUMED_ROLE_SCHEMA,
}

# Default RoleSessionName when the run supplies none (self-test path, or a
# secret without `role_session_name`). The collect path overrides this with a
# run-identifying value (req-aws-core-secret-aws-assumed-role-5).
DEFAULT_ROLE_SESSION_NAME = "tap-aws-core-collector"


class CredentialError(Exception):
    """The AWS secret is missing region scope or is otherwise unusable."""


def resolve_aws_secret(ref: SecretRef = AWS_SECRET_REF) -> Secret:
    """Resolve and validate the AWS collector secret (either supported kind).

    Dispatches on ``secret.kind``: ``aws_static_access_key`` or
    ``aws_assumed_role``. Each is validated against its ``aws_core``-owned
    schema. Raises ``SecretNotFoundError`` (missing) or ``SecretValidationError``
    (unsupported/wrong kind / bad ``data`` shape) from the secrets subsystem.
    """
    secret = resolve_secret(ref)
    if secret.kind not in _KIND_SCHEMAS:
        # Unsupported kind: let the harness raise the canonical redacted error.
        # (Only reachable when kind is neither of ours; this call always raises.)
        require_secret_kind(secret, AWS_SECRET_KIND, data_schema=AWS_STATIC_SCHEMA)
    require_secret_kind(secret, secret.kind, data_schema=_KIND_SCHEMAS[secret.kind])
    return secret


def is_assumed_role(data: Mapping[str, Any]) -> bool:
    """True when the resolved secret ``data`` describes a cross-account assume.

    Presence of ``role_arn`` is the discriminator: the two kinds' schemas are
    disjoint on it (the static kind forbids it via ``additionalProperties:
    false``), so a validated ``data`` carrying ``role_arn`` is unambiguously the
    ``aws_assumed_role`` kind.
    """
    return "role_arn" in data


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
    raise CredentialError("AWS secret defines no region: set data.regions_allowed (list) " "or data.region")


def build_session(creds: Mapping[str, Any]) -> boto3.session.Session:
    """A boto3 Session bound to a static credential set.

    ``creds`` is the ``aws_static_access_key`` kind's ``data`` (our own account)
    or the ``aws_assumed_role`` kind's ``data['base']`` (the identity that calls
    AssumeRole). Both carry ``access_key_id`` / ``secret_access_key`` / optional
    ``session_token``.
    """
    return boto3.session.Session(
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds.get("session_token"),
    )


def assume_role_session(
    base: boto3.session.Session,
    data: Mapping[str, Any],
    region: str,
    *,
    role_session_name: str | None = None,
    timeout_seconds: int | None = None,
) -> boto3.session.Session:
    """Assume ``data['role_arn']`` from ``base``; return a session on the
    returned short-lived credentials (cross-account collection).

    The External ID (``data['external_id']``) is always sent — the target role's
    trust policy requires it (req-aws-core-secret-aws-assumed-role-2). The
    returned session carries only STS-issued temporary credentials; nothing is
    persisted. ``RoleSessionName`` precedence: explicit arg → secret's
    ``role_session_name`` → ``DEFAULT_ROLE_SESSION_NAME``.
    """
    retries = {"max_attempts": 1}
    config = (
        Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries=retries,
        )
        if timeout_seconds is not None
        else Config(retries=retries)
    )
    sts = base.client("sts", region_name=region, config=config)
    kwargs: dict[str, Any] = {
        "RoleArn": data["role_arn"],
        "RoleSessionName": (role_session_name or data.get("role_session_name") or DEFAULT_ROLE_SESSION_NAME),
        "ExternalId": data["external_id"],
    }
    duration = data.get("duration_seconds")
    if duration:
        kwargs["DurationSeconds"] = duration
    creds = sts.assume_role(**kwargs)["Credentials"]
    return boto3.session.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def account_mismatch_error(data: Mapping[str, Any], account_id: str) -> str | None:
    """Assert-on-land: a message if the resolved account ≠ expected, else None.

    ``data['expected_account_id']`` is the operator's declaration of the target
    account; a mismatch means the assumed role landed somewhere unexpected
    (req-aws-core-secret-aws-assumed-role-4). Account ids are non-secret
    identifiers and are safe to surface in the message.
    """
    expected = data.get("expected_account_id")
    if expected and account_id != expected:
        return f"resolved AWS account {account_id} does not match the expected " f"account {expected}"
    return None


def client_factory(session: boto3.session.Session, region: str) -> Callable[[str], Any]:
    """A ``client_for(service)`` bound to ``region`` (for ``iter_source``)."""

    def client_for(service: str) -> Any:
        return session.client(service, region_name=region)

    return client_for


def caller_account_id(session: boto3.session.Session, region: str, *, timeout_seconds: int) -> str:
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
