"""WebAuthn ceremony wrappers over ``py_webauthn`` (req-tap-auth-passkey-webauthn).

TAP owns the ceremony: py_webauthn provides the crypto (the four ceremony functions)
and no user model. These wrappers pin the load-bearing ENFORCEMENT settings the
library leaves OFF by default (insecure-by-omission):

* user verification enforced at the VERIFY call (``require_user_verification=True``)
  on both registration and authentication (req-tap-auth-passkey-webauthn-3);
* the pinned RP-ID and an EXACT expected origin enforced every ceremony
  (req-tap-auth-passkey-webauthn-7);
* the stored sign count passed on every assertion so py_webauthn HARD-DENIES a
  regressed counter — a cloned-authenticator signal; 0/0 no-counter authenticators
  are exempt by the library — and the new count is persisted
  (req-tap-auth-passkey-webauthn-8);
* a discoverable assertion resolved by ``credential_id`` with the asserted
  ``userHandle`` confirmed against the owning user's stored handle before
  authenticating (req-tap-auth-passkey-webauthn-10).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from tap_auth.models import User, WebAuthnCredential, WebAuthnCredentialDeviceType, WebAuthnUserHandle
from tap_auth.passkey import config

logger = logging.getLogger(__name__)


class PasskeyCeremonyError(Exception):
    """A passkey ceremony could not be completed — verification failed, unknown
    credential, ``userHandle`` mismatch, or a clone/regression signal. Callers
    surface a single generic failure; the specific reason is logged, never returned
    to the client (non-enumerating)."""


def _redact(credential_id_b64: str) -> str:
    return "cred#" + hashlib.sha256(credential_id_b64.encode("utf-8")).hexdigest()[:12]


def registration_options(
    user_handle: bytes,
    *,
    user_label: str,
    display_name: str,
    exclude_credential_ids: list[str],
) -> tuple[str, bytes]:
    """Build discoverable + UV-required registration options for `user_handle`.

    ``user_handle`` is the opaque 64-byte WebAuthn user handle (the value the
    authenticator returns as ``userHandle`` on later assertions). It is passed as
    raw bytes rather than a :class:`WebAuthnUserHandle` row because for an
    ``enroll_first`` ceremony the user — and its handle row — does not exist yet;
    the redeem step persists this exact handle onto the freshly created user so the
    stored handle and the assertion's ``userHandle`` match (req-tap-auth-passkey-webauthn-10).

    Returns ``(options_json, challenge_bytes)``; stash the challenge server-side
    (:mod:`tap_auth.passkey.challenge`). ``exclude_credential_ids`` (base64url) set
    ``excludeCredentials`` so the same authenticator can't be double-registered
    (req-tap-auth-passkey-webauthn-15 / add-device-4).
    """
    options = generate_registration_options(
        rp_id=config.rp_id(),
        rp_name=config.rp_name(),
        user_id=user_handle,
        user_name=user_label,
        user_display_name=display_name or user_label,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)) for cid in exclude_credential_ids
        ],
    )
    return options_to_json(options), options.challenge


def bind_credential(
    user: User,
    credential: dict[str, Any],
    expected_challenge: bytes,
    *,
    device_label: str = "",
    transports: list[str] | None = None,
) -> WebAuthnCredential:
    """Verify a registration response (UV enforced at verify) and persist a new
    :class:`WebAuthnCredential` for `user` (keep-and-add). Records the BE/BS flags
    from the verification result. Raises :class:`PasskeyCeremonyError` on failure."""
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=config.rp_id(),
            expected_origin=config.expected_origins(),
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        logger.warning("[e2e9] passkey registration verification failed: %s", exc)
        raise PasskeyCeremonyError("registration verification failed") from exc

    device_type_value = getattr(verified.credential_device_type, "value", verified.credential_device_type)
    device_type = (
        WebAuthnCredentialDeviceType.MULTI_DEVICE
        if str(device_type_value) == "multi_device"
        else WebAuthnCredentialDeviceType.SINGLE_DEVICE
    )
    cred = WebAuthnCredential.objects.create(
        # TAP-CRED-BIND: pop-ceremony — verify_registration_response (UV enforced) ran above.
        user=user,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        aaguid=verified.aaguid or "",
        transports=list(transports or []),
        device_type=device_type,
        backed_up=bool(verified.credential_backed_up),
        device_label=device_label,
    )
    logger.info(
        "[9521] passkey registered: user=%s cred=%s device_type=%s backed_up=%s",
        user.pk,
        cred.redacted_credential_id,
        device_type,
        cred.backed_up,
    )
    return cred


def authentication_options() -> tuple[str, bytes]:
    """Build UV-required, usernameless (discoverable) authentication options.

    Returns ``(options_json, challenge_bytes)``. No ``allowCredentials`` — the user
    is intentionally unknown until the assertion verifies (req-tap-auth-passkey-webauthn-9).
    """
    options = generate_authentication_options(
        rp_id=config.rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json(options), options.challenge


def authenticate(credential: dict[str, Any], expected_challenge: bytes) -> User:
    """Resolve a discoverable assertion to its owning user and verify it.

    Resolves the credential by ``credential_id``, confirms the asserted
    ``userHandle`` equals the owner's stored handle (req-tap-auth-passkey-webauthn-10),
    then verifies with UV + the stored public key + stored sign count. py_webauthn
    hard-denies a regressed counter (clone signal), a wrong origin/RP-ID, a missing
    UV, and a bad signature — all as one ``InvalidAuthenticationResponse``, which we
    do NOT catch selectively (that would conflate clone vs forgery). Persists
    ``new_sign_count`` + ``last_used`` on success. Returns the ``User``; raises
    :class:`PasskeyCeremonyError` on any failure.
    """
    credential_id = credential.get("id") or credential.get("rawId")
    if not credential_id:
        raise PasskeyCeremonyError("assertion missing credential id")
    cred = WebAuthnCredential.objects.filter(credential_id=credential_id).select_related("user").first()
    if cred is None:
        logger.warning("[0b0f] passkey assertion for unknown credential id=%s", _redact(str(credential_id)))
        raise PasskeyCeremonyError("unknown credential")

    asserted_handle = (credential.get("response") or {}).get("userHandle")
    handle = WebAuthnUserHandle.objects.filter(user=cred.user).first()
    if handle is None or not asserted_handle or base64url_to_bytes(asserted_handle) != bytes.fromhex(handle.handle):
        logger.warning("[3d6f] passkey userHandle<->owner mismatch cred=%s", cred.redacted_credential_id)
        raise PasskeyCeremonyError("userHandle does not match credential owner")

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=config.rp_id(),
            expected_origin=config.expected_origins(),
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        logger.warning("[4094] passkey assertion denied cred=%s: %s", cred.redacted_credential_id, exc)
        raise PasskeyCeremonyError("assertion verification failed") from exc

    WebAuthnCredential.objects.filter(pk=cred.pk).update(
        # TAP-CRED-BIND: assertion-counter — sign_count/last_used only, after verified assertion; no rebind.
        sign_count=verified.new_sign_count,
        last_used=timezone.now(),
    )
    logger.info("[9015] passkey assertion ok user=%s cred=%s", cred.user_id, cred.redacted_credential_id)
    return cred.user
