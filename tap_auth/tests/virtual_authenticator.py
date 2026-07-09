"""A vendored, test-only WebAuthn authenticator (req-tap-auth-passkey-assurance).

py_webauthn's ``verify_*`` functions are the security seam TAP relies on, so the
assurance tests must drive the *real* library — which means producing genuine,
correctly-signed WebAuthn responses. Stock ``soft-webauthn`` cannot: it is
unmaintained (2022), pulls extra deps, and hardcodes user-verification **off**, so
with ``require_user_verification=True`` enforced everywhere every stock credential is
rejected and the happy path (register → log in) has zero coverage. The natural
"flip UV off in the wrapper" workaround would silently gut the top control.

So we vendor ~150 lines here instead: an ES256 (P-256) authenticator with the UP / UV
/ BE / BS flags and the sign counter and origin all controllable, so a test can emit a
UV-present credential (accepted), a UV-absent one (refused), a wrong-origin assertion,
a regressed-counter assertion (clone signal), etc. It builds attestation-``none``
registration objects and signed assertions to the WebAuthn spec; nothing here is
imported by production code.

Lineage: the CBOR/COSE/authData construction follows the W3C WebAuthn Level 2 spec
(§6.1 authenticator data, §6.5.2 none attestation) and the soft-webauthn approach.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url

# Authenticator-data flag bits (WebAuthn L2 §6.1).
_FLAG_UP = 0x01  # User Present
_FLAG_UV = 0x04  # User Verified
_FLAG_BE = 0x08  # Backup Eligible
_FLAG_BS = 0x10  # Backup State
_FLAG_AT = 0x40  # Attested credential data included

# COSE key constants for ES256 over P-256 (RFC 8152 / 9053).
_COSE_KTY = 1
_COSE_ALG = 3
_COSE_CRV = -1
_COSE_X = -2
_COSE_Y = -3
_KTY_EC2 = 2
_ALG_ES256 = -7
_CRV_P256 = 1


class VirtualAuthenticator:
    """A single virtual passkey authenticator holding one ES256 credential.

    Args:
        rp_id: RP-ID the credential is scoped to (its hash goes in authenticatorData).
        origin: the origin embedded in clientDataJSON (overridable per-call to forge
            an origin mismatch).
        uv: emit the User-Verified flag (set False to simulate a no-UV authenticator).
        be / bs: emit Backup-Eligible / Backup-State (a multi-device / synced passkey
            is BE+BS; a single-device one is neither). BS without BE is invalid per
            spec and py_webauthn rejects it — keep them consistent in tests.
        aaguid: 16-byte AAGUID (all-zero under attestation ``none``).
    """

    def __init__(
        self,
        *,
        rp_id: str,
        origin: str,
        uv: bool = True,
        be: bool = False,
        bs: bool = False,
        aaguid: bytes = b"\x00" * 16,
    ) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.uv = uv
        self.be = be
        self.bs = bs
        self.aaguid = aaguid
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.sign_count = 0

    # -- internal construction ------------------------------------------------

    def _flags(self, *, attested: bool) -> int:
        flags = _FLAG_UP  # user presence is always asserted
        if self.uv:
            flags |= _FLAG_UV
        if self.be:
            flags |= _FLAG_BE
        if self.bs:
            flags |= _FLAG_BS
        if attested:
            flags |= _FLAG_AT
        return flags

    def _cose_public_key(self) -> bytes:
        numbers = self._private_key.public_key().public_numbers()
        return cbor2.dumps(
            {
                _COSE_KTY: _KTY_EC2,
                _COSE_ALG: _ALG_ES256,
                _COSE_CRV: _CRV_P256,
                _COSE_X: numbers.x.to_bytes(32, "big"),
                _COSE_Y: numbers.y.to_bytes(32, "big"),
            }
        )

    def _authenticator_data(self, *, attested: bool, sign_count: int) -> bytes:
        rp_id_hash = hashlib.sha256(self.rp_id.encode("utf-8")).digest()
        data = rp_id_hash + bytes([self._flags(attested=attested)]) + sign_count.to_bytes(4, "big")
        if attested:
            cose = self._cose_public_key()
            data += self.aaguid + len(self.credential_id).to_bytes(2, "big") + self.credential_id + cose
        return data

    @staticmethod
    def _client_data(ceremony_type: str, challenge: bytes, origin: str) -> bytes:
        return json.dumps(
            {
                "type": ceremony_type,
                "challenge": bytes_to_base64url(challenge),
                "origin": origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    # -- public ceremony surface ---------------------------------------------

    def register(self, challenge: bytes, *, origin: str | None = None) -> dict[str, Any]:
        """Produce a registration response (attestation ``none``) for `challenge`."""
        client_data = self._client_data("webauthn.create", challenge, origin or self.origin)
        auth_data = self._authenticator_data(attested=True, sign_count=self.sign_count)
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation_object),
                "transports": ["internal"],
            },
        }

    def authenticate(
        self,
        challenge: bytes,
        *,
        user_handle: bytes,
        origin: str | None = None,
        sign_count: int | None = None,
    ) -> dict[str, Any]:
        """Produce a signed assertion for `challenge`.

        By default the internal counter increments each call (a well-behaved
        authenticator). Pass `sign_count` explicitly to forge a stall or regression
        (the clone signal py_webauthn hard-denies)."""
        if sign_count is None:
            self.sign_count += 1
            sign_count = self.sign_count
        client_data = self._client_data("webauthn.get", challenge, origin or self.origin)
        auth_data = self._authenticator_data(attested=False, sign_count=sign_count)
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self._private_key.sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_handle),
            },
        }
