"""AWS credential resolution for Steampipe collectors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tap_cares.secrets import SecretRef, require_secret_kind, resolve_secret

AWS_STATIC_ACCESS_KEY_KIND = "aws_static_access_key"

AWS_STATIC_ACCESS_KEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["access_key_id", "secret_access_key"],
    "additionalProperties": False,
    "properties": {
        "access_key_id": {"type": "string", "minLength": 1},
        "secret_access_key": {"type": "string", "minLength": 1},
        "session_token": {"type": "string", "minLength": 1},
        "region": {
            "type": "string",
            "pattern": r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$",
        },
    },
}


@dataclass(frozen=True, slots=True, repr=False)
class AwsStaticCredentials:
    """Resolved AWS static credentials.

    This object intentionally has no useful repr because it carries secret
    material. Pass it only across trusted runtime boundaries.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str = ""
    region: str = ""

    def as_steampipe_env(self, *, region: str) -> dict[str, str]:
        """Return environment variables for the Steampipe subprocess."""
        env = {
            "AWS_ACCESS_KEY_ID": self.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.secret_access_key,
            "AWS_REGION": region,
            "AWS_DEFAULT_REGION": region,
        }
        if self.session_token:
            env["AWS_SESSION_TOKEN"] = self.session_token
        return env

    def redaction_values(self) -> tuple[str, ...]:
        """Secret values that must be scrubbed from subprocess diagnostics."""
        values = [self.access_key_id, self.secret_access_key]
        if self.session_token:
            values.append(self.session_token)
        return tuple(values)


def resolve_aws_static_credentials(ref: SecretRef) -> AwsStaticCredentials:
    """Resolve and validate an AWS static credential secret."""
    secret = resolve_secret(ref)
    require_secret_kind(
        secret,
        AWS_STATIC_ACCESS_KEY_KIND,
        data_schema=AWS_STATIC_ACCESS_KEY_SCHEMA,
    )
    data = dict(secret.data)
    region = str(data.get("region") or "")
    if region and not _valid_region(region):
        # jsonschema should catch this; keep a defensive guard near use.
        region = ""
    return AwsStaticCredentials(
        access_key_id=str(data["access_key_id"]),
        secret_access_key=str(data["secret_access_key"]),
        session_token=str(data.get("session_token") or ""),
        region=region,
    )


def _valid_region(value: str) -> bool:
    return bool(re.fullmatch(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$", value))
