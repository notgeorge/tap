"""AWS Secrets Manager implementation of the TAP ``tap.secret_sources`` protocol.

Resolves a secret's value from AWS Secrets Manager using **ambient cloud IAM** — the
instance role via boto3's default credential chain — never a TAP secret, so there is no
resolution recursion (``req-plugin-depres-bootstrap-3``). boto3 lives in this contributed
distribution and is imported lazily inside :meth:`fetch`, so importing this module costs
nothing and TAP core never carries the AWS SDK (``req-plugin-depres-sources-3``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


class AwsSecretsManagerSource:
    """Fetch a secret value from AWS Secrets Manager.

    Routing token ``aws_secrets_manager`` (a manifest names it in ``metadata.source``).
    The manifest's ``metadata.source_ref`` must carry ``secret_id`` (the Secrets Manager
    name or ARN); an optional ``region`` overrides the ambient region. The stored
    ``SecretString`` is parsed as JSON and returned as the envelope ``data`` — so what the
    store holds is exactly what an on-disk manifest would have held inline (for the git
    source credential: ``{"token": ..., "host": ..., "username": ...}``).
    """

    name = "aws_secrets_manager"

    def fetch(self, ref: Mapping[str, Any], *, scope: str, key: str) -> Mapping[str, Any]:
        """Return the value for ``scope``/``key`` located by ``ref`` (``source_ref``)."""
        secret_id = ref.get("secret_id")
        if not isinstance(secret_id, str) or not secret_id:
            raise ValueError(f"aws_secrets_manager source for {scope}:{key} requires a non-empty source_ref.secret_id")
        region = ref.get("region")
        if region is not None and not isinstance(region, str):
            raise ValueError(f"aws_secrets_manager source_ref.region for {scope}:{key} must be a string")

        import boto3  # lazy: keep the SDK off the import path; only fetch() needs it

        client = boto3.client("secretsmanager", region_name=region) if region else boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_id)

        raw = response.get("SecretString")
        if raw is None:
            raise ValueError(
                f"secret '{secret_id}' for {scope}:{key} has no SecretString (binary secrets are unsupported)"
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"secret '{secret_id}' for {scope}:{key} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"secret '{secret_id}' for {scope}:{key} must be a JSON object, got {type(data).__name__}")
        return data


__all__ = ["AwsSecretsManagerSource"]
