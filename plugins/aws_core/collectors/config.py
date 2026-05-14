"""Configuration helpers for the AWS Steampipe collector."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from tap_cares.secrets import SecretRef

AWS_STEAMPIPE_COLLECTOR_SETTING = "AWS_CORE_STEAMPIPE_COLLECTOR"

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
_PARTITIONS = {"aws", "aws-us-gov", "aws-cn"}


class AwsSteampipeConfigError(ValueError):
    """Raised when AWS Steampipe collector configuration is invalid."""


@dataclass(frozen=True, slots=True)
class AwsSteampipeCollectorConfig:
    """JSON-safe v0 target configuration for the AWS Steampipe collector."""

    target_key: str
    account_id: str
    partition: str
    secret_ref: SecretRef
    regions: tuple[str, ...]
    profile: str

    @classmethod
    def from_mapping(cls, value: Any) -> AwsSteampipeCollectorConfig:
        if not isinstance(value, dict):
            raise AwsSteampipeConfigError("AWS Steampipe collector config must be an object.")

        target_key = value.get("target_key")
        if not _valid_token(target_key):
            raise AwsSteampipeConfigError("target_key must be a non-empty registry token.")

        account_id = value.get("account_id")
        if not isinstance(account_id, str) or not _ACCOUNT_ID_RE.fullmatch(account_id):
            raise AwsSteampipeConfigError("account_id must be a 12 digit AWS account ID string.")

        partition = value.get("partition", "aws")
        if partition not in _PARTITIONS:
            allowed = ", ".join(sorted(_PARTITIONS))
            raise AwsSteampipeConfigError(f"partition must be one of: {allowed}.")

        regions = _parse_regions(value.get("regions"))

        profile = value.get("profile")
        if not _valid_token(profile):
            raise AwsSteampipeConfigError("profile must be a non-empty registry token.")

        return cls(
            target_key=target_key,
            account_id=account_id,
            partition=partition,
            secret_ref=_parse_secret_ref(value.get("secret_ref")),
            regions=regions,
            profile=profile,
        )

    def to_context(self) -> dict[str, Any]:
        """Return a redaction-safe context payload for run records."""
        return {
            "target_key": self.target_key,
            "account_id": self.account_id,
            "partition": self.partition,
            "secret_ref": _secret_ref_context(self.secret_ref),
            "regions": list(self.regions),
            "profile": self.profile,
        }


def load_aws_steampipe_collector_config(
    settings_obj: Any = settings,
) -> AwsSteampipeCollectorConfig:
    """Load the v0 AWS Steampipe collector config from Django settings."""

    if not hasattr(settings_obj, AWS_STEAMPIPE_COLLECTOR_SETTING):
        raise AwsSteampipeConfigError(
            f"Missing Django setting {AWS_STEAMPIPE_COLLECTOR_SETTING}."
        )
    return AwsSteampipeCollectorConfig.from_mapping(
        getattr(settings_obj, AWS_STEAMPIPE_COLLECTOR_SETTING)
    )


def _parse_regions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise AwsSteampipeConfigError("regions must be a non-empty list of region names.")
    regions: list[str] = []
    for region in value:
        if not _valid_region(region):
            raise AwsSteampipeConfigError("regions must contain only non-empty AWS region strings.")
        if region not in regions:
            regions.append(region)
    return tuple(regions)


def _parse_secret_ref(value: Any) -> SecretRef:
    if not isinstance(value, dict):
        raise AwsSteampipeConfigError("secret_ref must be an object with scope and key.")
    scope = value.get("scope")
    key = value.get("key")
    if not _valid_token(scope):
        raise AwsSteampipeConfigError("secret_ref.scope must be a non-empty registry token.")
    if not _valid_token(key):
        raise AwsSteampipeConfigError("secret_ref.key must be a non-empty registry token.")
    return SecretRef(scope=scope, key=key)


def _secret_ref_context(secret_ref: SecretRef) -> dict[str, str]:
    return {"scope": secret_ref.scope, "key": secret_ref.key}


def _valid_token(value: Any) -> bool:
    return isinstance(value, str) and bool(_TOKEN_RE.fullmatch(value))


def _valid_region(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$", value))
