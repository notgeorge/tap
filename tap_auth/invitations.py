"""Invitation mint + redeem — the TAP-owned enrollment chokepoint (req-tap-auth-passkey-enrollment).

Two-layer mint (mirrors the service-boundary gateway/_impl pattern):

* :func:`_mint_invitation` — the UNGUARDED impl (token hygiene: public-id/secret
  split, >=128-bit CSPRNG, hashed-at-rest, TTL with an enforced maximum). Genesis /
  boot bootstrap calls this directly BELOW the capability gate — genesis is the root
  of trust and sits beneath the authz system, exactly like ``ensure_initial_admin``
  (req-tap-auth-passkey-genesis / the "attribution, not authority" model).
* :func:`mint_invitation` — the GATED public entry point: ``authorize`` on
  ``auth.manage_users`` then delegate. Runtime admins (e.g. ``enroll-user``) and a
  future web UI use this, with the human admin as caller.

:func:`redeem_invitation` verifies the secret with a constant-time compare against a
by-public-id lookup (never a by-secret query — a timing leak), collapses every
failure to one generic message, and — in a single transaction — atomically consumes
the invitation (``pending -> consumed`` guarded on ``rowcount == 1``), creates/loads
the user, binds the passkey, and applies grants. A failed ceremony rolls the whole
thing back, leaving the invitation ``pending`` (still redeemable).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from tap_auth.models import Invitation, InvitationAction, InvitationStatus, User, UserKind, WebAuthnUserHandle
from tap_auth.passkey import ceremony
from tap_auth.policy import authorize
from tap_auth.roles import is_login_grantable
from tap_grid.caller_context import CallerContext

logger = logging.getLogger(__name__)

CAP_MANAGE_USERS = "auth.manage_users"

# TTLs: genesis is short; a general invite is at most a day. The maximum is ENFORCED
# (a longer TTL fails, it does not warn-and-proceed) — req-tap-auth-passkey-enrollment-2.
GENESIS_TTL = timedelta(hours=1)
DEFAULT_TTL = timedelta(hours=24)
MAX_TTL = timedelta(hours=24)

_PUBLIC_ID_BYTES = 8  # 16 hex chars — non-secret, log-safe lookup handle
_SECRET_BYTES = 32  # 256-bit, well above the >=128-bit floor
# Fixed-length dummy hash so the constant-time compare runs even when the public-id
# does not resolve (non-enumerating: an unknown id is indistinguishable from a wrong
# secret) — req-tap-auth-passkey-enrollment-6.
_SENTINEL_HASH = hashlib.sha256(b"tap-invitation-nonexistent-sentinel").hexdigest()

GENERIC_FAILURE = "invalid or expired invitation"


class InvitationError(Exception):
    """A redemption failed. The message is deliberately generic for client-facing
    failures (:data:`GENERIC_FAILURE`); the specific reason is logged, not returned."""


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class UsernameTaken(ValueError):
    """A pinned ``username`` already resolves to an existing :class:`User`.

    Raised at mint (fail fast) and again at redeem (the mint→redeem window is a real
    TOCTOU gap — the account can appear in between). A pinned username is **create-only**:
    it must never silently become an additive mint onto someone else's account, which is
    why `req-tap-auth-passkey-add-device-1` makes adding a credential an explicit flag.
    """


def _assert_username_free(username: str) -> None:
    """Fail loud if a pinned username is taken. Never suffix-and-continue: silently
    landing on `admin-3f2c` would defeat the caller's entire reason for pinning."""
    if username and User.objects.filter(username=username).exists():
        raise UsernameTaken(
            f"username '{username}' already exists — a pinned username is create-only and will not "
            "silently bind a credential to an existing account. To add a passkey to an existing user, "
            "use the explicit add-credential path (req-tap-auth-passkey-add-device)."
        )


def _mint_invitation(
    *,
    action: str,
    email: str = "",
    display_name: str = "",
    username: str = "",
    grants: list[str] | None = None,
    target_user: User | None = None,
    issued_by: User | None = None,
    ttl: timedelta = DEFAULT_TTL,
) -> tuple[Invitation, str]:
    """UNGUARDED mint impl (token hygiene). Genesis/bootstrap calls this directly
    below the capability gate. Returns ``(invitation, raw_secret)`` — the raw secret
    is returned exactly once and is never persisted (only its hash).

    ``username`` pins the created user's username instead of deriving it from the email
    (req-tap-auth-passkey-enrollment-8); empty preserves the derived behaviour exactly."""
    if ttl > MAX_TTL:
        raise ValueError(f"invitation TTL {ttl} exceeds the enforced maximum {MAX_TTL}")
    if username and action != InvitationAction.ENROLL_FIRST:
        raise ValueError(f"username may only be pinned on an {InvitationAction.ENROLL_FIRST} invitation")
    _assert_username_free(username)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    invitation = Invitation.objects.create(
        public_id=secrets.token_hex(_PUBLIC_ID_BYTES),
        secret_hash=_hash_secret(secret),
        action=action,
        email=email,
        display_name=display_name,
        username=username,
        grants=list(grants or []),
        target_user=target_user,
        issued_by=issued_by,
        expires_at=timezone.now() + ttl,
        status=InvitationStatus.PENDING,
    )
    logger.info(
        "[f866] invitation minted public_id=%s action=%s issued_by=%s expires=%s",
        invitation.public_id,
        action,
        getattr(issued_by, "pk", None),
        invitation.expires_at.isoformat(),
    )
    return invitation, secret


def mint_invitation(
    caller_ctx: CallerContext,
    *,
    action: str,
    email: str = "",
    display_name: str = "",
    username: str = "",
    grants: list[str] | None = None,
    target_user: User | None = None,
    ttl: timedelta = DEFAULT_TTL,
) -> tuple[Invitation, str]:
    """GATED mint (runtime admins / web UI). Authorizes ``auth.manage_users`` then
    delegates to :func:`_mint_invitation`, attributing ``issued_by`` to the caller."""
    authorize(caller_ctx, CAP_MANAGE_USERS, operation="invite.mint")
    # authorize() guarantees a concrete, authenticated actor (not None/anonymous), so
    # the caller is a real User — attribute issued_by to them.
    issued_by = caller_ctx.user
    assert isinstance(issued_by, User)
    return _mint_invitation(
        action=action,
        email=email,
        display_name=display_name,
        username=username,
        grants=grants,
        target_user=target_user,
        issued_by=issued_by,
        ttl=ttl,
    )


def mint_below_gate_as_bootloader(
    *,
    action: str,
    email: str = "",
    display_name: str = "",
    username: str = "",
    grants: list[str] | None = None,
    target_user: User | None = None,
    ttl: timedelta = GENESIS_TTL,
) -> tuple[Invitation, str]:
    """Mint an invitation BELOW the capability gate, attributed to ``tap_bootloader``.

    The shared genesis-class mint used by `enroll_admin` and `bootstrap_dev_passkey`: on a
    fresh instance no capability-holding human exists to authorize a mint, so bootstrap sits
    beneath authz (exactly like ``sync.ensure_initial_admin``). ``issued_by`` names the
    bootloader for a truthful audit trail — **attribution, not authority**: the bootloader
    does not and must not hold ``auth.manage_users``.

    Factored out so the two callers cannot drift on who gets credited for a below-the-gate
    mint. Raises :class:`MissingActor` (as a plain error) if auth sync has not run — an
    unattributable invitation is refused, never minted anonymously.
    """
    # Imported lazily: tap_auth.actors reads the DB, and invitations.py is imported at
    # module scope by views/commands that must not touch the DB at import time.
    from tap_auth.actors import BOOTLOADER, get_builtin_actor

    bootloader = get_builtin_actor(BOOTLOADER)
    assert isinstance(bootloader, User)
    return _mint_invitation(
        action=action,
        email=email,
        display_name=display_name,
        username=username,
        grants=grants,
        target_user=target_user,
        issued_by=bootloader,
        ttl=ttl,
    )


def _unique_username(seed: str) -> str:
    """A unique Django username derived from a seed (email/local part). Username is
    DB-unique; email is not identity, so we never key off it — this is just a
    deterministic-ish handle with a random suffix on collision."""
    base = (seed or "user").strip()[:120] or "user"
    if not User.objects.filter(username=base).exists():
        return base
    while True:
        candidate = f"{base}-{secrets.token_hex(4)}"[:150]
        if not User.objects.filter(username=candidate).exists():
            return candidate


def _create_enrolled_user(invitation: Invitation, user_handle: bytes) -> User:
    """Create the passkey-native user for an ``enroll_first`` redemption, from the
    SERVER-STORED invitation only. Passwordless: ``set_unusable_password`` so the
    account has no usable password (req-tap-auth-passkey-recovery-7 / honesty edge).

    ``user_handle`` is the exact handle the registration ceremony used as ``user.id``;
    it is persisted onto the new user's :class:`WebAuthnUserHandle` so the stored
    handle matches the ``userHandle`` future assertions return (webauthn-10). It must
    NOT be regenerated here — a fresh random handle would never match the credential.

    A pinned :attr:`Invitation.username` is used verbatim; it is re-checked for freeness
    here because mint and redeem are separated in time and the account can appear in
    between. Inside the redeem transaction, so raising rolls the consume back and leaves
    the invitation pending rather than burning it (req-tap-auth-passkey-enrollment-8)."""
    if invitation.username:
        _assert_username_free(invitation.username)
        username = invitation.username
    else:
        username = _unique_username(invitation.email)
    user = User(
        username=username,
        email=invitation.email,
        user_kind=UserKind.HUMAN,
    )
    user.set_unusable_password()
    user.save()
    WebAuthnUserHandle.objects.create(
        # TAP-CRED-BIND: pre-registration-handle — handle only (no key), minted at user genesis.
        user=user,
        handle=user_handle.hex(),
    )
    return user


def _apply_grants(user: User, grants: list[str]) -> None:
    """Apply role grants the same 3 ways the social adapter does — guard, resolve
    the Django Group, add membership — but FAIL LOUD (roll back) if a granted role's
    Group is missing. For genesis a silently-skipped grant would leave a powerless
    "admin" that falsely satisfies the last-admin invariant (Hardening / decision #2)."""
    for role in grants:
        if not is_login_grantable(role):
            raise InvitationError(f"role '{role}' is not human-assignable")
        try:
            group = Group.objects.get(name=role)
        except Group.DoesNotExist as exc:
            raise InvitationError(f"role group '{role}' does not exist (grant would be a no-op)") from exc
        user.groups.add(group)


def load_redeemable(public_id: str, secret: str) -> Invitation:
    """Constant-time secret check + status/expiry gate, shared by the begin-registration
    endpoint and :func:`redeem_invitation`.

    Looks up by PUBLIC id only and runs the ``hmac.compare_digest`` against a fixed
    sentinel hash even when the id does not resolve, so an unknown public-id and a
    wrong secret are timing-indistinguishable (req-tap-auth-passkey-enrollment-6).
    Returns the pending invitation or raises the generic :class:`InvitationError`.
    """
    invitation = Invitation.objects.filter(public_id=public_id).first()
    reference_hash = invitation.secret_hash if invitation is not None else _SENTINEL_HASH
    secret_ok = hmac.compare_digest(reference_hash, _hash_secret(secret))
    if invitation is None or not secret_ok:
        logger.warning("[224e] invitation lookup failed (unknown id or bad secret) public_id=%s", public_id)
        raise InvitationError(GENERIC_FAILURE)
    if invitation.status != InvitationStatus.PENDING or invitation.expires_at <= timezone.now():
        logger.warning(
            "[aec2] invitation not redeemable (status/expiry) public_id=%s status=%s",
            public_id,
            invitation.status,
        )
        raise InvitationError(GENERIC_FAILURE)
    return invitation


def redeem_invitation(
    public_id: str,
    secret: str,
    *,
    credential: dict[str, Any],
    expected_challenge: bytes,
    user_handle: bytes,
) -> User:
    """Redeem an invitation and bind the first/additional passkey atomically.

    ``user_handle`` is the exact opaque handle the registration ceremony used as
    ``user.id`` (stashed with the challenge). For ``enroll_first`` it is persisted
    onto the new user so the stored handle matches future assertions' ``userHandle``.

    Returns the bound user (NOT logged in — the caller finalizes via
    ``auth.login`` to cycle the session key, req-tap-auth-passkey-webauthn-11).
    Raises :class:`InvitationError` (generic) on any failure; a failed ceremony
    rolls back so the invitation stays ``pending``.
    """
    invitation = load_redeemable(public_id, secret)

    with transaction.atomic():
        # Atomic single-use consume: pending -> consumed, guarded on rowcount so a
        # parallel redeem of the same token loses the race (req-tap-auth-passkey-enrollment-2).
        consumed = Invitation.objects.filter(pk=invitation.pk, status=InvitationStatus.PENDING).update(
            status=InvitationStatus.CONSUMED,
            consumed_at=timezone.now(),
        )
        if consumed != 1:
            logger.warning("[c6e5] invitation redeem lost the consume race public_id=%s", public_id)
            raise InvitationError(GENERIC_FAILURE)

        # Identity/grants/handle come from the SERVER row, never client input.
        if invitation.action == InvitationAction.ADD_CREDENTIAL:
            user = invitation.target_user
            # Guaranteed non-null by the add_credential check constraint + clean().
            assert user is not None
        else:
            # A pinned username taken since mint (TOCTOU) is a real failure, but it must
            # not escape as a bare ValueError: every caller of this function handles the
            # single generic InvitationError. Roll back (invitation stays pending), log
            # the specific reason, return the generic one.
            try:
                user = _create_enrolled_user(invitation, user_handle)
            except UsernameTaken as exc:
                logger.warning("[aba2] invitation redeem hit a taken pinned username public_id=%s: %s", public_id, exc)
                raise InvitationError(GENERIC_FAILURE) from exc

        # Bind the passkey INSIDE the transaction: a verification failure raises and
        # rolls back the consume, leaving the invitation redeemable. Convert the
        # ceremony failure to the one generic InvitationError so every caller (the
        # enroll view included) handles a SINGLE failure type — the specific reason
        # was already logged at the ceremony boundary, never surfaced to the client.
        try:
            credential_obj = ceremony.bind_credential(user, credential, expected_challenge)
        except ceremony.PasskeyCeremonyError as exc:
            logger.warning("[acb9] invitation redeem ceremony failed public_id=%s: %s", public_id, exc)
            raise InvitationError(GENERIC_FAILURE) from exc

        if invitation.action == InvitationAction.ENROLL_FIRST:
            _apply_grants(user, list(invitation.grants or []))

    logger.info(
        "[940d] invitation redeemed public_id=%s user=%s cred=%s action=%s",
        public_id,
        user.pk,
        credential_obj.redacted_credential_id,
        invitation.action,
    )
    return user
