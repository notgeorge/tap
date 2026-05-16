"""Secret-discovered collection target for the AWS Steampipe collector.

The collector is zero-config (spec-aws-steampipe-collector-v0.md
`req-aws-steampipe-secret-discovery`). It resolves a single well-known
`SecretRef` and reads everything it needs — credentials, region, account —
from that secret. There is no config object, Django setting, environment
variable, or UI. The deprecated env/Django-setting config object
(`req-aws-steampipe-config`, "ENV-Based Collector Config") is removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from plugins.aws_core.collectors.credentials import (
    AwsStaticCredentials,
    resolve_aws_static_credentials,
)
from tap_cares.secrets import SecretRef, resolve_secret

# The single well-known secret this collector resolves (point lookup, never
# enumeration). Operator file: ``aws/steampipe-collector.secret.json`` under
# ``TAP_SECRETS_ROOT``.
AWS_STEAMPIPE_SECRET_REF = SecretRef(scope="aws", key="steampipe-collector")

# Hardcoded v0 collection scope label (not operator-selectable; the old
# operator-facing "profile" knob is removed).
AWS_COLLECTION_SCOPE = "vpc-subnet-v0"

_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
_REGION_RE = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$")


class AwsSteampipeConfigError(ValueError):
    """Raised when the resolved AWS secret cannot describe a usable target.

    This is consumer validation layered on top of the generic
    ``aws_static_access_key`` secret schema: the collector additionally
    requires ``data.region`` and ``metadata.account_id`` and accepts an
    optional ``metadata.target_regions`` downscope list.
    """


@dataclass(frozen=True, slots=True)
class AwsCollectionTarget:
    """The collection target, fully derived from the well-known secret."""

    account_id: str
    primary_region: str
    regions: tuple[str, ...]
    credentials: AwsStaticCredentials

    def to_context(self) -> dict[str, Any]:
        """Return a redaction-safe context payload for run records.

        Never includes credential material — that lives only on
        ``credentials`` and is scrubbed from diagnostics via
        ``credentials.redaction_values()``.
        """
        return {
            "account_id": self.account_id,
            "primary_region": self.primary_region,
            "regions": list(self.regions),
            "scope": AWS_COLLECTION_SCOPE,
            "secret_ref": AWS_STEAMPIPE_SECRET_REF.qualified,
        }


def resolve_aws_collection_target() -> AwsCollectionTarget:
    """Resolve the well-known secret into a collection target.

    Raises:
        tap_cares.exceptions.SecretNotFoundError: the well-known secret file
            was not loaded (no matching ``*.secret.json`` mounted at startup).
        tap_cares.exceptions.SecretError: the secret exists but is the wrong
            kind or fails the AWS credential data schema.
        AwsSteampipeConfigError: the secret is a valid credential but does
            not carry the collector-required ``data.region`` /
            ``metadata.account_id`` (or ``metadata.target_regions`` is
            malformed).
    """
    # resolve_secret raises SecretNotFoundError when absent; resolve_aws_static
    # _credentials additionally validates kind + data schema (SecretError).
    secret = resolve_secret(AWS_STEAMPIPE_SECRET_REF)
    credentials = resolve_aws_static_credentials(AWS_STEAMPIPE_SECRET_REF)

    primary_region = credentials.region
    if not primary_region:
        raise AwsSteampipeConfigError(
            "The AWS collector secret must set data.region (the primary "
            "collection region); it is missing or not a valid AWS region."
        )

    account_id = str(secret.metadata.get("account_id") or "")
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        raise AwsSteampipeConfigError(
            "The AWS collector secret must set metadata.account_id to the "
            "12-digit AWS account ID the operator intends to collect."
        )

    regions = _parse_target_regions(
        secret.metadata.get("target_regions"), primary_region
    )

    return AwsCollectionTarget(
        account_id=account_id,
        primary_region=primary_region,
        regions=regions,
        credentials=credentials,
    )


def _parse_target_regions(value: Any, primary_region: str) -> tuple[str, ...]:
    """Parse the optional ``metadata.target_regions`` downscope list.

    Absent ⇒ collect only the primary region. This is an interim stopgap
    until a durable collector-configuration object exists
    (`req-aws-steampipe-config-object`, Backlog).
    """
    if value is None:
        return (primary_region,)
    if not isinstance(value, list) or not value:
        raise AwsSteampipeConfigError(
            "metadata.target_regions, when present, must be a non-empty list "
            "of AWS region names."
        )
    regions: list[str] = []
    for region in value:
        if not isinstance(region, str) or not _REGION_RE.fullmatch(region):
            raise AwsSteampipeConfigError(
                "metadata.target_regions must contain only valid AWS region "
                f"names; got {region!r}."
            )
        if region not in regions:
            regions.append(region)
    return tuple(regions)
