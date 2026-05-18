"""tap_cares runtime secrets (spec-tap-cares-secrets.md).

Public surface for capability code:

    from tap_cares.secrets import SecretRef, resolve_secret, require_secret_kind

    ref = SecretRef("aws", "prod-readonly")
    secret = resolve_secret(ref)
    # The kind name and `data_schema` are owned and supplied by the consuming
    # plugin/collector, not by tap_cares (req-tap-cares-secrets-consumer-kinds).
    require_secret_kind(secret, "aws_static_access_key", data_schema=consumer_schema)

The secrets subsystem is intentionally narrow: load `*.secret.json` files from
a configured mounted root at Django startup into an in-process registry,
expose typed helpers for resolution and consumer-side validation, and provide
a recursive redactor so diagnostic payloads do not leak secret material.

Direct access to `secret_registry` is reserved for the secrets subsystem and
tests.
"""

from tap_cares.secrets.loader import load_secrets
from tap_cares.secrets.models import Secret, SecretRef
from tap_cares.secrets.redaction import redact
from tap_cares.secrets.registry import resolve_secret, secret_registry
from tap_cares.secrets.validation import require_secret_kind

__all__ = [
    "Secret",
    "SecretRef",
    "load_secrets",
    "redact",
    "require_secret_kind",
    "resolve_secret",
    "secret_registry",
]
