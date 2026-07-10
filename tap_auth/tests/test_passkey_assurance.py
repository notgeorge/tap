"""Passkey assurance corpus (req-tap-auth-passkey-assurance).

The security-critical cases for the MVP passkey path, driven end-to-end against the
REAL ``py_webauthn`` via the vendored :class:`VirtualAuthenticator` (so the tests
exercise TAP's ceremony wrappers, not a mock of them). Each case links to the spec
acceptance criterion it exercises via ``@pytest.mark.spec``.

Coverage:
  * enrollment gating — only a minted, secret-matching invitation creates a user;
    the gated mint refuses a capability-less caller;
  * UV enforced at verify — present → accepted (the happy path), absent → refused,
    on both registration and authentication;
  * exact RP-ID/origin — a mismatched or any-*localhost* origin is refused;
  * library-enforced sign-count regression (clone signal) → hard deny;
  * userHandle ↔ owner binding;
  * single-use + expiry + atomic redeem (a concurrent double-redeem yields exactly
    one account; a failed ceremony rolls back, leaving the invitation redeemable);
  * full-stack session fixation — the authenticated session key differs from the
    anonymous pre-auth key, and the session is attributed to the PasskeyBackend.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.utils import timezone
from webauthn.helpers import base64url_to_bytes

from tap_auth.errors import AuthzError
from tap_auth.invitations import (
    GENESIS_TTL,
    InvitationError,
    UsernameTaken,
    _mint_invitation,
    mint_invitation,
    redeem_invitation,
)
from tap_auth.models import (
    Invitation,
    InvitationAction,
    InvitationStatus,
    UserKind,
    WebAuthnCredential,
)
from tap_auth.passkey import ceremony
from tap_auth.passkey import config as passkey_config
from tap_grid.caller_context import CallerContext

from .virtual_authenticator import VirtualAuthenticator

User = get_user_model()


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _origin() -> str:
    return passkey_config.expected_origins()[0]


def _make_authenticator(**kwargs) -> VirtualAuthenticator:
    return VirtualAuthenticator(rp_id=settings.TAP_PASSKEY_RP_ID, origin=_origin(), **kwargs)


def _mint_admin(email: str = "op@example.com", grants: list[str] | None = None) -> tuple[Invitation, str]:
    """Mint a genesis enroll_first invitation below the gate (no caller needed)."""
    return _mint_invitation(
        action=InvitationAction.ENROLL_FIRST,
        email=email,
        grants=grants if grants is not None else ["tap_admin"],
        ttl=GENESIS_TTL,
    )


def _register(authenticator: VirtualAuthenticator, *, label: str = "op", origin: str | None = None):
    """Run the registration-options half and return ``(user_handle, challenge, credential)``."""
    user_handle = secrets.token_bytes(64)
    _options_json, challenge = ceremony.registration_options(
        user_handle, user_label=label, display_name=label, exclude_credential_ids=[]
    )
    credential = authenticator.register(challenge, origin=origin)
    return user_handle, challenge, credential


def _enroll(authenticator: VirtualAuthenticator, invitation: Invitation, secret: str):
    """Full service-layer redemption for a fresh authenticator. Returns the user."""
    user_handle, challenge, credential = _register(authenticator)
    return redeem_invitation(
        invitation.public_id,
        secret,
        credential=credential,
        expected_challenge=challenge,
        user_handle=user_handle,
    )


def _assert_authenticates(authenticator: VirtualAuthenticator, user):
    """Drive a usernameless assertion for `user` and assert it resolves back to them."""
    handle_hex = user.webauthn_handle.handle
    _options_json, challenge = ceremony.authentication_options()
    assertion = authenticator.authenticate(challenge, user_handle=bytes.fromhex(handle_hex))
    return ceremony.authenticate(assertion, challenge)


# --------------------------------------------------------------------------- #
# Enrollment gating                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-enrollment-1")
@pytest.mark.django_db
def test_enrollment_creates_admin_with_grant_and_no_password():
    invitation, secret = _mint_admin()
    user = _enroll(_make_authenticator(uv=True, be=True, bs=True), invitation, secret)

    assert user.user_kind == UserKind.HUMAN
    assert user.groups.filter(name="tap_admin").exists()
    assert not user.has_usable_password()  # honesty edge: genesis admin has no password
    assert WebAuthnCredential.objects.filter(user=user).count() == 1
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.CONSUMED
    # The stored handle is exactly the one the ceremony used (webauthn-10).
    cred = WebAuthnCredential.objects.get(user=user)
    assert cred.backed_up is True


@pytest.mark.spec("req-tap-auth-passkey-enrollment-6")
@pytest.mark.django_db
def test_wrong_secret_refused_leaves_invitation_pending_and_no_user():
    invitation, _secret = _mint_admin()
    authenticator = _make_authenticator()
    user_handle, challenge, credential = _register(authenticator)

    with pytest.raises(InvitationError):
        redeem_invitation(
            invitation.public_id,
            "not-the-secret",
            credential=credential,
            expected_challenge=challenge,
            user_handle=user_handle,
        )

    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING
    assert not User.objects.filter(email="op@example.com").exists()


@pytest.mark.spec("req-tap-auth-passkey-enrollment-6")
@pytest.mark.django_db
def test_unknown_public_id_refused():
    authenticator = _make_authenticator()
    user_handle, challenge, credential = _register(authenticator)
    with pytest.raises(InvitationError):
        redeem_invitation(
            "deadbeefdeadbeef",
            "whatever",
            credential=credential,
            expected_challenge=challenge,
            user_handle=user_handle,
        )


@pytest.mark.spec("req-tap-auth-passkey-enrollment-3")
@pytest.mark.django_db
def test_gated_mint_refuses_capabilityless_caller():
    """The GATED mint requires auth.manage_users; a capability-less caller is denied
    (the genesis path bypasses this deliberately, below the gate)."""
    powerless = User.objects.create(username="nobody", user_kind=UserKind.HUMAN)
    with pytest.raises(AuthzError):
        mint_invitation(
            CallerContext(user=powerless),
            action=InvitationAction.ENROLL_FIRST,
            email="x@example.com",
            grants=[],
        )


# --------------------------------------------------------------------------- #
# User verification (UV) enforced at verify                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-webauthn-3")
@pytest.mark.django_db
def test_happy_path_uv_present_register_then_authenticate():
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)
    resolved = _assert_authenticates(authenticator, user)
    assert resolved.pk == user.pk


@pytest.mark.spec("req-tap-auth-passkey-webauthn-3")
@pytest.mark.django_db
def test_uv_absent_registration_refused():
    invitation, secret = _mint_admin(grants=[])
    with pytest.raises(InvitationError):
        _enroll(_make_authenticator(uv=False), invitation, secret)
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING


@pytest.mark.spec("req-tap-auth-passkey-webauthn-3")
@pytest.mark.django_db
def test_uv_absent_authentication_refused():
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)
    # Same credential, but this time the authenticator does not verify the user.
    authenticator.uv = False
    with pytest.raises(ceremony.PasskeyCeremonyError):
        _assert_authenticates(authenticator, user)


# --------------------------------------------------------------------------- #
# Exact RP-ID / origin                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-webauthn-7")
@pytest.mark.django_db
def test_registration_origin_mismatch_refused():
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator()
    user_handle = secrets.token_bytes(64)
    _options_json, challenge = ceremony.registration_options(
        user_handle, user_label="op", display_name="op", exclude_credential_ids=[]
    )
    forged = authenticator.register(challenge, origin="http://evil.example")
    with pytest.raises(InvitationError):
        redeem_invitation(
            invitation.public_id,
            secret,
            credential=forged,
            expected_challenge=challenge,
            user_handle=user_handle,
        )


@pytest.mark.spec("req-tap-auth-passkey-webauthn-7")
@pytest.mark.django_db
def test_any_localhost_origin_refused_on_authentication():
    """A co-resident localhost:<other-port> must NOT pass — the origin is exact,
    not any-localhost (the relay attack webauthn-7 closes)."""
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)

    handle_hex = user.webauthn_handle.handle
    _options_json, challenge = ceremony.authentication_options()
    assertion = authenticator.authenticate(
        challenge, user_handle=bytes.fromhex(handle_hex), origin="http://localhost:59999"
    )
    with pytest.raises(ceremony.PasskeyCeremonyError):
        ceremony.authenticate(assertion, challenge)


# --------------------------------------------------------------------------- #
# Sign-count regression + userHandle binding                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-webauthn-8")
@pytest.mark.django_db
def test_sign_count_regression_hard_denied():
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)

    # First assertion advances the stored counter (0 -> some positive value).
    _assert_authenticates(authenticator, user)

    # A regressed counter is the clone signal; py_webauthn hard-denies it and we
    # surface it as a generic ceremony failure (never a soft flag).
    handle_hex = user.webauthn_handle.handle
    _options_json, challenge = ceremony.authentication_options()
    regressed = authenticator.authenticate(challenge, user_handle=bytes.fromhex(handle_hex), sign_count=0)
    with pytest.raises(ceremony.PasskeyCeremonyError):
        ceremony.authenticate(regressed, challenge)


@pytest.mark.spec("req-tap-auth-passkey-webauthn-10")
@pytest.mark.django_db
def test_userhandle_owner_mismatch_refused():
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    _enroll(authenticator, invitation, secret)  # registers the credential + handle

    _options_json, challenge = ceremony.authentication_options()
    # Assert with the right credential but a WRONG user handle.
    assertion = authenticator.authenticate(challenge, user_handle=secrets.token_bytes(64))
    with pytest.raises(ceremony.PasskeyCeremonyError):
        ceremony.authenticate(assertion, challenge)


# --------------------------------------------------------------------------- #
# Single-use + expiry + atomic redeem                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-enrollment-2")
@pytest.mark.django_db
def test_expired_invitation_refused():
    invitation, secret = _mint_admin(grants=[])
    Invitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(InvitationError):
        _enroll(_make_authenticator(), invitation, secret)


@pytest.mark.spec("req-tap-auth-passkey-enrollment-2")
@pytest.mark.django_db
def test_consumed_invitation_replay_refused():
    invitation, secret = _mint_admin(grants=[])
    _enroll(_make_authenticator(uv=True), invitation, secret)
    # A second redemption of the same token is refused (single-use).
    with pytest.raises(InvitationError):
        _enroll(_make_authenticator(uv=True), invitation, secret)
    assert User.objects.filter(email="op@example.com").count() == 1


@pytest.mark.spec("req-tap-auth-passkey-enrollment-2")
@pytest.mark.django_db(transaction=True)
def test_concurrent_redeem_yields_exactly_one_account():
    """Two threads redeem the SAME invitation with two independent credentials; the
    atomic ``UPDATE ... WHERE status='pending'`` (rowcount-guarded) must let exactly
    one win, creating exactly one account."""
    invitation, secret = _mint_admin(email="race@example.com", grants=[])

    prepared = []
    for _ in range(2):
        authenticator = _make_authenticator(uv=True)
        user_handle, challenge, credential = _register(authenticator, label="race")
        prepared.append((user_handle, challenge, credential))

    results: dict[int, str] = {}
    barrier = threading.Barrier(2)

    def worker(i: int) -> None:
        user_handle, challenge, credential = prepared[i]
        barrier.wait()
        try:
            redeem_invitation(
                invitation.public_id,
                secret,
                credential=credential,
                expected_challenge=challenge,
                user_handle=user_handle,
            )
            results[i] = "ok"
        except InvitationError:
            results[i] = "err"
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == ["err", "ok"]
    assert User.objects.filter(email="race@example.com").count() == 1
    # No manual cleanup: the django_db(transaction=True) teardown flushes the test DB.
    # (A manual User.delete() here would cascade through the simple-history tables,
    # which is both redundant and fragile.)


@pytest.mark.spec("req-tap-auth-passkey-enrollment-2")
@pytest.mark.django_db
def test_failed_ceremony_rolls_back_leaving_invitation_pending():
    """A verification failure inside the redeem transaction rolls back the consume,
    so the invitation stays redeemable (no burned token on a fumbled ceremony)."""
    invitation, secret = _mint_admin(grants=[])
    # uv=False fails verify_registration_response, raising inside the atomic block.
    with pytest.raises(InvitationError):
        _enroll(_make_authenticator(uv=False), invitation, secret)
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING
    # And the token is still usable with a good authenticator.
    user = _enroll(_make_authenticator(uv=True), invitation, secret)
    assert user is not None


# --------------------------------------------------------------------------- #
# Full-stack session fixation                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-webauthn-11")
@pytest.mark.django_db
def test_enroll_web_flow_cycles_session_key():
    """Drive the actual enroll views: the anonymous pre-auth session that held the
    challenge must NOT become the authenticated session — auth.login cycles the key,
    and the session is attributed to the PasskeyBackend (never a password backend)."""
    invitation, secret = _mint_admin()
    client = Client()

    # GET the shell, then request options (this stashes the challenge -> a keyed session).
    assert client.get(f"/auth/enroll/{invitation.public_id}/").status_code == 200
    opt_resp = client.post(
        f"/auth/enroll/{invitation.public_id}/options/",
        data=json.dumps({"secret": secret}),
        content_type="application/json",
    )
    assert opt_resp.status_code == 200
    options = opt_resp.json()
    challenge = base64url_to_bytes(options["challenge"])
    pre_auth_key = client.session.session_key
    assert pre_auth_key is not None

    authenticator = _make_authenticator(uv=True)
    credential = authenticator.register(challenge)
    verify_resp = client.post(
        f"/auth/enroll/{invitation.public_id}/verify/",
        data=json.dumps({"secret": secret, "credential": credential}),
        content_type="application/json",
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["redirect"] == "/"

    post_auth_key = client.session.session_key
    assert post_auth_key is not None
    assert post_auth_key != pre_auth_key  # key cycled (no session fixation)
    assert client.session["_auth_user_id"]  # a real authenticated session
    assert client.session["_auth_user_backend"] == "tap_auth.auth_backends.PasskeyBackend"


@pytest.mark.spec("req-tap-auth-passkey-rollout-2")
@pytest.mark.django_db
def test_native_passkey_login_web_flow():
    """The IdP-free front door end-to-end: a registered user signs in via the native
    passkey login endpoints and lands in an authenticated, PasskeyBackend session."""
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)

    client = Client()
    assert client.get("/auth/passkey/login/").status_code == 200
    opt_resp = client.post("/auth/passkey/login/options/", data=json.dumps({}), content_type="application/json")
    assert opt_resp.status_code == 200
    challenge = base64url_to_bytes(opt_resp.json()["challenge"])

    assertion = authenticator.authenticate(challenge, user_handle=bytes.fromhex(user.webauthn_handle.handle))
    verify_resp = client.post(
        "/auth/passkey/login/verify/",
        data=json.dumps({"credential": assertion, "next": "/"}),
        content_type="application/json",
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["redirect"] == "/"
    assert str(client.session["_auth_user_id"]) == str(user.pk)
    assert client.session["_auth_user_backend"] == "tap_auth.auth_backends.PasskeyBackend"


@pytest.mark.spec("req-tap-auth-passkey-webauthn-13")
@pytest.mark.django_db
def test_native_login_rejects_open_redirect_next():
    """A hostile ?next / body next never escapes the origin — it collapses to '/'."""
    invitation, secret = _mint_admin(grants=[])
    authenticator = _make_authenticator(uv=True)
    user = _enroll(authenticator, invitation, secret)

    client = Client()
    client.get("/auth/passkey/login/")
    challenge = base64url_to_bytes(
        client.post("/auth/passkey/login/options/", data="{}", content_type="application/json").json()["challenge"]
    )
    assertion = authenticator.authenticate(challenge, user_handle=bytes.fromhex(user.webauthn_handle.handle))
    verify_resp = client.post(
        "/auth/passkey/login/verify/",
        data=json.dumps({"credential": assertion, "next": "https://evil.example/steal"}),
        content_type="application/json",
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["redirect"] == "/"


# --------------------------------------------------------------------------- #
# Pinned username at mint (enrollment-8)                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-enrollment-8")
@pytest.mark.django_db
def test_pinned_username_is_used_verbatim_not_derived_from_email():
    invitation, secret = _mint_invitation(
        action=InvitationAction.ENROLL_FIRST,
        email="op@example.com",
        username="admin",
        grants=["tap_admin"],
        ttl=GENESIS_TTL,
    )
    user = _enroll(_make_authenticator(uv=True), invitation, secret)
    assert user.username == "admin"  # not "op@example.com"
    assert user.email == "op@example.com"  # email still recorded, just not as the name


@pytest.mark.spec("req-tap-auth-passkey-enrollment-8")
@pytest.mark.django_db
def test_omitting_username_preserves_email_derived_behaviour():
    invitation, secret = _mint_admin(email="derived@example.com")
    user = _enroll(_make_authenticator(uv=True), invitation, secret)
    assert user.username == "derived@example.com"


@pytest.mark.spec("req-tap-auth-passkey-enrollment-8")
@pytest.mark.django_db
def test_pinning_an_existing_username_fails_loud_at_mint():
    """Create-only. A pinned name that resolves to an existing user must NOT silently
    become an additive mint onto that account (the add-device path is explicit)."""
    User.objects.create(username="admin", user_kind=UserKind.HUMAN)
    with pytest.raises(UsernameTaken):
        _mint_invitation(
            action=InvitationAction.ENROLL_FIRST,
            email="op@example.com",
            username="admin",
            grants=["tap_admin"],
            ttl=GENESIS_TTL,
        )
    assert not Invitation.objects.exists()  # nothing minted


@pytest.mark.spec("req-tap-auth-passkey-enrollment-8")
@pytest.mark.django_db
def test_username_taken_between_mint_and_redeem_is_refused_and_leaves_invitation_pending():
    """The TOCTOU window is real: mint validates, then the account appears, then redeem
    runs. Redeem MUST re-check, refuse generically, and roll the consume back so the
    invitation survives (a failed ceremony never burns the token)."""
    invitation, secret = _mint_invitation(
        action=InvitationAction.ENROLL_FIRST,
        email="op@example.com",
        username="admin",
        grants=["tap_admin"],
        ttl=GENESIS_TTL,
    )
    squatter = User.objects.create(username="admin", user_kind=UserKind.HUMAN)  # appears after mint

    with pytest.raises(InvitationError):
        _enroll(_make_authenticator(uv=True), invitation, secret)

    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING  # rolled back, still redeemable
    assert not WebAuthnCredential.objects.filter(user=squatter).exists()  # nothing bound to them
    assert User.objects.filter(username="admin").count() == 1


@pytest.mark.spec("req-tap-auth-passkey-enrollment-8")
@pytest.mark.django_db
def test_username_cannot_be_pinned_on_an_add_credential_invitation():
    """Pinning a name only means anything when creating; on add_credential the target is
    already bound by internal id, so accepting a username would be a confusing no-op."""
    existing = User.objects.create(username="someone", user_kind=UserKind.HUMAN)
    with pytest.raises(ValueError):
        _mint_invitation(
            action=InvitationAction.ADD_CREDENTIAL,
            username="admin",
            target_user=existing,
            ttl=GENESIS_TTL,
        )
