"""Guided dev passkey onboarding — `manage.py bootstrap_dev_passkey`.

Covers req-tap-auth-passkey-dev-bootstrap-9…-14: one command as the single implementation,
readiness by validation rather than a stat, stream discipline, caller-owned placement,
opt-in waiting, and register-once/replay agreeing on one account.

The headline test is `test_guided_first_run_round_trips_onto_the_dev_admin`: it drives the
whole documented flow — register through the REAL enroll views with a virtual authenticator,
emit the record, wipe the session, re-import — and asserts the same credential lands back on
`admin`. That is the flow a new developer performs on their first hour, and it was
*unreachable* before this change: `admin` already exists (spawn's password bridge) so
`enroll_first` refuses as create-only, while `add_credential` crashed on a missing
`WebAuthnUserHandle`.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from webauthn.helpers import base64url_to_bytes

from tap_auth.models import Invitation, InvitationAction, User, UserKind, WebAuthnCredential, WebAuthnUserHandle
from tap_auth.passkey import config as passkey_config
from tap_auth.passkey.dev_record import DEV_ADMIN_USERNAME

from .virtual_authenticator import VirtualAuthenticator

_DEV_PROFILE = "core_dev"  # a shipped profile classified dev_local
_DEPLOYABLE_PROFILE = "core"  # unclassified -> import refused, fail closed


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _run(*args, **kwargs) -> tuple[str, str]:
    """Invoke the command, returning (stdout, stderr) captured separately — the whole
    point of the stream-discipline contract is that these two never mix."""
    out, err = io.StringIO(), io.StringIO()
    call_command("bootstrap_dev_passkey", *args, stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


def _state(*args) -> dict[str, Any]:
    out, _err = _run("--json", *args)
    state: dict[str, Any] = json.loads(out)
    return state


def _make_authenticator(**kwargs) -> VirtualAuthenticator:
    return VirtualAuthenticator(rp_id=settings.TAP_PASSKEY_RP_ID, origin=passkey_config.expected_origins()[0], **kwargs)


def _password_bridge_admin() -> User:
    """The `admin` spawn's Step 6 leaves behind: a real account, with a usable password,
    and — the part that broke registration — no WebAuthn user handle."""
    return User.objects.create_user(username=DEV_ADMIN_USERNAME, password="bridge", user_kind=UserKind.HUMAN)


def _register_through_the_web(invitation: Invitation, secret: str, authenticator: VirtualAuthenticator) -> None:
    """Drive the real enroll views, exactly as the developer's browser does."""
    client = Client()
    assert client.get(f"/auth/enroll/{invitation.public_id}/").status_code == 200
    opt_resp = client.post(
        f"/auth/enroll/{invitation.public_id}/options/",
        data=json.dumps({"secret": secret}),
        content_type="application/json",
    )
    assert opt_resp.status_code == 200, opt_resp.content
    challenge = base64url_to_bytes(opt_resp.json()["challenge"])
    credential = authenticator.register(challenge)
    verify_resp = client.post(
        f"/auth/enroll/{invitation.public_id}/verify/",
        data=json.dumps({"secret": secret, "credential": credential}),
        content_type="application/json",
    )
    assert verify_resp.status_code == 200, verify_resp.content


def _pending_invitation() -> Invitation:
    """The invitation `--register` just minted. Its secret never leaves stderr, so tests
    recover the secret from the printed link — the DB stores only its hash."""
    return Invitation.objects.latest("issued_at")


# --------------------------------------------------------------------------- #
# State resolution (dev-bootstrap-9, -10)                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-9")
@pytest.mark.django_db
def test_state_is_not_dev_under_a_deployable_profile():
    state = _state("--profile", _DEPLOYABLE_PROFILE)
    assert state["state"] == "not_dev"
    assert state["profile_kind"] is None  # unclassified -> fail closed


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-9")
@pytest.mark.django_db
def test_every_action_is_refused_under_a_deployable_profile():
    for action in ("--register", "--import", "--emit-record"):
        with pytest.raises(CommandError):
            _run(action, "--profile", _DEPLOYABLE_PROFILE)
    assert not Invitation.objects.exists()  # --register minted nothing


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-10")
@pytest.mark.django_db
def test_a_zero_byte_record_is_needs_registration_not_ready(tmp_path):
    """The landmine: a failed `> record` redirect truncates the target before the command
    runs. `[[ -f ]]` calls that ready; only validation calls it what it is."""
    empty = tmp_path / "admin.dev-passkey.json"
    empty.write_text("")
    state = _state("--profile", _DEV_PROFILE, "--record", str(empty))
    assert state["state"] == "needs_registration"
    assert "unusable" in state["detail"]


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-10")
@pytest.mark.django_db
def test_a_corrupt_record_is_needs_registration_not_ready(tmp_path):
    corrupt = tmp_path / "admin.dev-passkey.json"
    corrupt.write_text(json.dumps({"version": 1, "rp_id": "localhost"}))  # valid JSON, wrong shape
    state = _state("--profile", _DEV_PROFILE, "--record", str(corrupt))
    assert state["state"] == "needs_registration"


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-10")
@pytest.mark.django_db
def test_a_missing_record_is_needs_registration(tmp_path):
    state = _state("--profile", _DEV_PROFILE, "--record", str(tmp_path / "absent.json"))
    assert state["state"] == "needs_registration"
    assert state["detail"] == "no record on disk"


# --------------------------------------------------------------------------- #
# Stream discipline (dev-bootstrap-11)                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-11")
@pytest.mark.django_db
def test_register_writes_the_secret_bearing_link_to_stderr_never_stdout():
    """A caller redirecting stdout into a file must never capture the one-time secret."""
    _password_bridge_admin()
    stdout, stderr = _run("--register", "--profile", _DEV_PROFILE)
    assert stdout == ""  # nothing at all — a redirect captures an empty file
    assert "/auth/enroll/" in stderr and "#" in stderr


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-11")
@pytest.mark.django_db
def test_json_state_is_the_only_thing_on_stdout():
    stdout, _stderr = _run("--json", "--profile", _DEV_PROFILE)
    json.loads(stdout)  # parses cleanly with no narration prefix/suffix


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-11")
@pytest.mark.django_db
def test_status_read_is_never_a_failure_and_prints_nothing_to_stdout():
    """Spawn calls the no-flag form on every boot; it must exit 0 and stay off stdout."""
    stdout, stderr = _run("--profile", _DEV_PROFILE)  # no action flags, no exception
    assert stdout == ""
    assert "State:" in stderr


# --------------------------------------------------------------------------- #
# Register-once → replay round trip (dev-bootstrap-14)                         #
# --------------------------------------------------------------------------- #


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-14")
@pytest.mark.django_db
def test_register_targets_the_existing_admin_as_add_credential_not_a_second_user():
    """`admin` already exists (password bridge), so registration is keep-and-add onto it —
    never a second account, never a re-grant."""
    admin = _password_bridge_admin()
    _run("--register", "--profile", _DEV_PROFILE)

    invitation = _pending_invitation()
    assert invitation.action == InvitationAction.ADD_CREDENTIAL
    assert invitation.target_user == admin
    assert invitation.grants == []
    assert User.objects.filter(username=DEV_ADMIN_USERNAME).count() == 1


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-14")
@pytest.mark.django_db
def test_register_on_a_fresh_instance_pins_the_username_to_the_replay_target():
    """No `admin` yet (a truly fresh instance): enroll_first, with the username PINNED so
    the account register-once creates is the account replay binds onto."""
    _run("--register", "--profile", _DEV_PROFILE)
    invitation = _pending_invitation()
    assert invitation.action == InvitationAction.ENROLL_FIRST
    assert invitation.username == DEV_ADMIN_USERNAME
    assert invitation.grants == ["tap_admin"]


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-14")
@pytest.mark.django_db
def test_add_credential_mints_a_handle_for_a_password_era_admin():
    """The handle-less-admin bug: `enroll_options` used `WebAuthnUserHandle.objects.get`,
    which raises for an account that never registered a passkey — i.e. every password-era
    admin, including the one this whole flow targets."""
    admin = _password_bridge_admin()
    assert not WebAuthnUserHandle.objects.filter(user=admin).exists()

    _, stderr = _run("--register", "--profile", _DEV_PROFILE)
    invitation = _pending_invitation()
    secret = stderr.split("#")[1].split("\n")[0].strip()

    _register_through_the_web(invitation, secret, _make_authenticator(uv=True))

    assert WebAuthnUserHandle.objects.filter(user=admin).exists()
    assert WebAuthnCredential.objects.filter(user=admin).count() == 1


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-14")
@pytest.mark.django_db
def test_guided_first_run_round_trips_onto_the_dev_admin(tmp_path):
    """The whole documented flow, end to end: register once through the real views, emit the
    record, simulate a fresh spawn, replay. The SAME credential id lands back on `admin` —
    which is what "register once, replay everywhere" actually claims."""
    admin = _password_bridge_admin()

    # 1. register (guided) — the link goes to stderr, the developer opens it
    _, stderr = _run("--register", "--profile", _DEV_PROFILE)
    invitation = _pending_invitation()
    secret = stderr.split("#")[1].split("\n")[0].strip()
    _register_through_the_web(invitation, secret, _make_authenticator(uv=True))
    original_cred_id = WebAuthnCredential.objects.get(user=admin).credential_id

    # 2. emit the record — stdout carries ONLY the JSON, so `> record` is safe
    stdout, _ = _run("--emit-record", "--profile", _DEV_PROFILE)
    record_path = tmp_path / "admin.dev-passkey.json"
    record_path.write_text(stdout)

    # the caller placed it; now the state machine agrees it is usable
    assert _state("--profile", _DEV_PROFILE, "--record", str(record_path))["state"] == "ready"

    # 3. simulate a fresh spawn: drop the credential + handle (not the User — a delete
    #    cascades through simple-history and is fragile under the full lane)
    WebAuthnCredential.objects.all().delete()
    WebAuthnUserHandle.objects.all().delete()

    # 4. replay
    _run("--import", "--profile", _DEV_PROFILE, "--record", str(record_path))

    replayed = WebAuthnCredential.objects.get(user__username=DEV_ADMIN_USERNAME)
    assert replayed.credential_id == original_cred_id
    assert replayed.user.groups.filter(name="tap_admin").exists()


@pytest.mark.spec("req-tap-auth-passkey-dev-bootstrap-13")
@pytest.mark.django_db
def test_wait_times_out_rather_than_hanging(tmp_path):
    """A developer who walks away gets a bounded, explicit failure — never a hung spawn."""
    _password_bridge_admin()
    with pytest.raises(CommandError, match="timed out"):
        _run("--wait", "--timeout", "1", "--profile", _DEV_PROFILE)
