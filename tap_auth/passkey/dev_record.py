"""Dev passkey record — export / load / gated import (req-tap-auth-passkey-dev-bootstrap).

The dev-only "register once, replay forever" path. The operator registers a `localhost`
passkey once, exports the PUBLIC credential record (:func:`build_dev_record`), and every
freshly-spawned dev session binds that same passkey with no re-registration
(:func:`import_dev_admin`) — the one-gesture dev login that exercises the real passkey
path instead of a password bridge.

Two guards are the ENTIRE trust basis of import (it creates an admin + binds a credential
with zero proof-of-possession and no human interaction — there is no attestation and no
challenge-response at import):

* :func:`assert_dev_import_allowed` — the **allowlist** gate. Import is permitted ONLY
  under an explicitly ``dev_local``-classified boot profile; missing/unknown/customer/
  deploy all refuse (fail closed). Never keyed off ``DEBUG``; ``TAP_TEST_MODE`` is not an
  enabler here (req-tap-auth-passkey-dev-bootstrap-4).
* :func:`load_dev_record` integrity check — schema validation (shape) PLUS a canonical
  self-digest (corruption detection). The load-bearing anti-tamper mitigation is the file
  living 0600 in an operator-owned dir; the same-uid residual is NAMED, not defended here
  (req-tap-auth-passkey-dev-bootstrap-8).

Confidentiality of the record is low-stakes (no private key); its INTEGRITY is what matters.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.contrib.auth.models import Group
from django.utils import timezone

from tap.boot_records import canonical_digest_bytes
from tap.jsonfiles import JsonFileError, load_json_file
from tap_auth.models import User, UserKind, WebAuthnCredential, WebAuthnCredentialDeviceType, WebAuthnUserHandle
from tap_auth.roles import is_login_grantable

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "dev-passkey-record.schema.json"

# The one allowlisted profile classification that permits dev import. An EXPLICIT value —
# anything else (customer/deploy/unclassified/typo) fails closed (req-…-dev-bootstrap-4).
PROFILE_KIND_DEV_LOCAL = "dev_local"

# The dev admin the replayed passkey binds to. Matches the spawn password-bridge username
# so the dev passkey lands on the same familiar `admin` account (add-a-credential, not a
# second admin).
DEV_ADMIN_USERNAME = "admin"

RECORD_VERSION = 1
_ADMIN_ROLE = "tap_admin"


class DevRecordError(Exception):
    """The dev passkey record could not be loaded, validated, or its integrity verified."""


class DevImportNotAllowed(Exception):
    """Dev passkey import was refused because the active profile is not explicitly
    ``dev_local`` (the `exemption_not_allowed` assurance class, req-…-dev-bootstrap-4)."""


# --------------------------------------------------------------------------- #
# Allowlist gate                                                              #
# --------------------------------------------------------------------------- #


def assert_dev_import_allowed(profile_kind: str | None) -> None:
    """Permit dev passkey import ONLY under an explicitly ``dev_local`` profile.

    Allowlist, not denylist: any missing/unknown/customer/deploy classification is
    refused (fail closed), so an unclassified or typo'd profile cannot slip through.
    Deliberately does NOT consult ``settings.DEBUG`` (legitimately True in non-test
    instances) and ``TAP_TEST_MODE`` is not an enabler — reaching this already required
    shell access, and the gate is re-evaluated on every invocation."""
    if profile_kind != PROFILE_KIND_DEV_LOCAL:
        raise DevImportNotAllowed(
            f"--import-dev-passkey is permitted only under an explicitly '{PROFILE_KIND_DEV_LOCAL}' "
            f"boot profile; active classification is {profile_kind!r} (refused, fail closed). "
            "Dev passkey replay is a developer-local affordance and must never run on a "
            "customer/deploy or unclassified profile."
        )


# --------------------------------------------------------------------------- #
# Integrity + (de)serialization                                              #
# --------------------------------------------------------------------------- #


def _integrity_digest(record: dict[str, Any]) -> str:
    """Canonical sha256 over the record with the ``integrity`` object removed — the one
    canonicalization definition (:func:`tap.boot_records.canonical_digest_bytes`), so a
    cosmetic reformat does not move the digest; only real content changes do."""
    without = {k: v for k, v in record.items() if k != "integrity"}
    # canonical_digest_bytes re-canonicalizes (sorted keys, tight separators), so any valid
    # JSON encoding of `without` hashes identically — plain json.dumps is enough here.
    return canonical_digest_bytes(json.dumps(without).encode("utf-8"))


def build_dev_record(*, user_handle_hex: str, credential: WebAuthnCredential) -> dict[str, Any]:
    """Serialize the PUBLIC dev passkey record from a registered credential + its handle.

    Captures the registration's user handle (replayed so every session's admin shares it)
    and the public credential material only — never any private key. Stamps the corruption-
    detection self-digest last."""
    device_type_value = getattr(credential.device_type, "value", credential.device_type)
    record: dict[str, Any] = {
        "version": RECORD_VERSION,
        "rp_id": "localhost",
        "origin_policy": "per_session_localhost_exact",
        "user_handle": user_handle_hex,
        "credential": {
            "credential_id": credential.credential_id,
            "public_key": credential.public_key,
            "sign_count": int(credential.sign_count),
            "aaguid": credential.aaguid or "",
            "transports": list(credential.transports or []),
            "device_type": str(device_type_value),
            "backed_up": bool(credential.backed_up),
        },
        "exported_at": timezone.now().isoformat(),
    }
    record["integrity"] = {"digest_alg": "sha256", "digest": _integrity_digest(record)}
    return record


def load_dev_record(path: str | Path) -> dict[str, Any]:
    """Read + schema-validate + integrity-verify a dev passkey record. Fail-closed.

    Schema validation checks SHAPE; the self-digest catches corruption. Neither proves
    authenticity — that rests on the file's 0600 operator-owned integrity + the dev/local
    allowlist gate. Raises :class:`DevRecordError` on any problem."""
    path = Path(path)
    if not path.is_file():
        raise DevRecordError(f"dev passkey record not found: {path}")
    try:
        record = load_json_file(path, schema=_SCHEMA_PATH)
    except JsonFileError as exc:
        logger.warning("[14c3] dev passkey record failed schema validation path=%s: %s", path, exc)
        raise DevRecordError(f"dev passkey record is invalid: {exc}") from exc
    if not isinstance(record, dict):
        raise DevRecordError("dev passkey record must be a JSON object")

    declared = record["integrity"]["digest"]
    computed = _integrity_digest(record)
    if declared != computed:
        logger.warning("[28c6] dev passkey record integrity mismatch path=%s (corrupt/tampered)", path)
        raise DevRecordError(
            "dev passkey record integrity digest does not match its content "
            "(corrupted or tampered) — refusing to import."
        )
    return record


# --------------------------------------------------------------------------- #
# Import (below the capability gate)                                          #
# --------------------------------------------------------------------------- #


def import_dev_admin(record: dict[str, Any], *, username: str = DEV_ADMIN_USERNAME) -> User:
    """Bind the record's passkey onto the dev admin (idempotent), granting ``tap_admin``.

    Below the capability gate (root-of-trust bootstrap, like genesis): binds the credential
    directly with NO ceremony — import substitutes the already-verified record for the
    registration proof-of-possession. Get-or-creates the ``admin`` user, pins its
    WebAuthnUserHandle to the record's handle so future assertions resolve, and
    update-or-creates the credential (re-spawn just refreshes it). Grants ``tap_admin``
    fail-loud (a missing group would be a powerless admin). Callers MUST have already run
    :func:`assert_dev_import_allowed`."""
    cred = record["credential"]

    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": "", "user_kind": UserKind.HUMAN},
    )
    if created:
        # A dev admin WE mint authenticates with the passkey only — no usable password
        # (mirrors the enrollment path's set_unusable_password honesty edge). Django treats
        # an empty password as usable, so this is not a no-op. We deliberately do NOT touch
        # an EXISTING account's password: when import binds onto the spawn password-bridge
        # admin, that fallback survives until password retirement is done globally.
        user.set_unusable_password()
        user.save(update_fields=["password"])
    # Pin the handle to the record's — all of the dev admin's credentials share it, and it
    # must equal the discoverable credential's userHandle for the assertion to resolve.
    WebAuthnUserHandle.objects.update_or_create(user=user, defaults={"handle": record["user_handle"]})
    device_type = (
        WebAuthnCredentialDeviceType.MULTI_DEVICE
        if cred["device_type"] == "multi_device"
        else WebAuthnCredentialDeviceType.SINGLE_DEVICE
    )
    credential_obj, _ = WebAuthnCredential.objects.update_or_create(
        credential_id=cred["credential_id"],
        defaults={
            "user": user,
            "public_key": cred["public_key"],
            "sign_count": cred["sign_count"],
            "aaguid": cred.get("aaguid", ""),
            "transports": list(cred.get("transports", [])),
            "device_type": device_type,
            "backed_up": bool(cred.get("backed_up", False)),
            "device_label": "dev-replay",
        },
    )
    _grant_admin(user)
    logger.info(
        "[eb22] dev passkey imported: user=%s cred=%s device_type=%s",
        user.pk,
        credential_obj.redacted_credential_id,
        device_type,
    )
    return user


def _grant_admin(user: User) -> None:
    """Ensure the dev admin holds ``tap_admin`` — fail loud if the group is missing (a
    silently-skipped grant would leave a powerless 'admin'; mirrors the genesis grant)."""
    if not is_login_grantable(_ADMIN_ROLE):
        raise DevRecordError(f"role '{_ADMIN_ROLE}' is not human-assignable")
    try:
        group = Group.objects.get(name=_ADMIN_ROLE)
    except Group.DoesNotExist as exc:
        raise DevRecordError(f"role group '{_ADMIN_ROLE}' does not exist (grant would be a no-op)") from exc
    user.groups.add(group)
