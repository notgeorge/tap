"""Genesis enrollment + last-admin invariant (req-tap-auth-passkey-genesis).

The ``enroll_admin`` command is the below-the-gate bootstrap: on a fresh instance it
mints the first admin's passkey invitation attributed to ``tap_bootloader`` (attribution,
not authority), and the boot last-admin invariant recognizes that pending invitation as
a path to admin so a freshly-minted-but-unredeemed instance does not fail closed.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from tap_auth.actors import BOOTLOADER, get_builtin_actor
from tap_auth.boot import _pending_admin_invitation_exists
from tap_auth.invitations import _mint_invitation
from tap_auth.models import Invitation, InvitationAction, InvitationStatus


@pytest.mark.spec("req-tap-auth-passkey-genesis-4")
@pytest.mark.django_db
def test_enroll_admin_mints_pending_tap_admin_invitation_attributed_to_bootloader():
    out = StringIO()
    call_command("enroll_admin", "--email", "founder@example.com", "--print-token", stdout=out)

    invitation = Invitation.objects.get(email="founder@example.com")
    assert invitation.action == InvitationAction.ENROLL_FIRST
    assert invitation.status == InvitationStatus.PENDING
    assert invitation.grants == ["tap_admin"]
    # issued_by is the bootloader program actor — a truthful audit trail, not authority.
    assert invitation.issued_by_id == get_builtin_actor(BOOTLOADER).pk

    printed = out.getvalue()
    assert f"/auth/enroll/{invitation.public_id}" in printed
    assert "#" in printed  # the one-time secret rides the fragment


@pytest.mark.spec("req-tap-auth-passkey-genesis-4")
@pytest.mark.django_db
def test_enroll_admin_without_print_token_withholds_the_secret():
    out = StringIO()
    call_command("enroll_admin", "--email", "quiet@example.com", stdout=out)
    invitation = Invitation.objects.get(email="quiet@example.com")
    printed = out.getvalue()
    # The public id is shown, but no secret-bearing enrollment link.
    assert invitation.public_id in printed
    assert "#" not in printed


@pytest.mark.spec("req-tap-auth-passkey-genesis-3")
@pytest.mark.django_db
def test_pending_admin_invitation_detected_by_last_admin_invariant_helper():
    assert _pending_admin_invitation_exists() is False
    _mint_invitation(action=InvitationAction.ENROLL_FIRST, email="a@example.com", grants=["tap_admin"])
    assert _pending_admin_invitation_exists() is True


@pytest.mark.spec("req-tap-auth-passkey-genesis-3")
@pytest.mark.django_db
def test_non_admin_pending_invitation_does_not_satisfy_invariant():
    _mint_invitation(action=InvitationAction.ENROLL_FIRST, email="viewer@example.com", grants=["tap_viewer"])
    assert _pending_admin_invitation_exists() is False
