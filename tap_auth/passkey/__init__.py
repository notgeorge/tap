"""Native WebAuthn passkey method (req-tap-auth-passkey-webauthn).

TAP owns the ceremony, credential storage, and login/enroll flows on top of
``py_webauthn`` (crypto core only — no user model), so a passkey deployment needs
no IdP and shares no code with allauth. Submodules:

* :mod:`tap_auth.passkey.config` — RP-ID / exact expected origin (from settings).
* :mod:`tap_auth.passkey.challenge` — server-side single-use, TTL'd challenge store.
* :mod:`tap_auth.passkey.ceremony` — the four ceremony wrappers pinning the
  enforcement settings py_webauthn leaves off by default, plus credential bind +
  discoverable-assertion resolution.
"""
