"""`manage.py enroll_admin` — genesis: mint the first admin's passkey invitation.

The root-of-trust bootstrap for a passwordless, zero-IdP instance: on a fresh install
there is no human who can log in, so there is no capability-holding caller to authorize
minting an invitation. Genesis therefore sits BELOW the capability gate — exactly like
:func:`tap_auth.sync.ensure_initial_admin`, which creates today's first admin with
direct ORM and no ``authorize`` (auth bootstrap is a sanctioned out-of-scope exception,
the same class as migrations). This command calls the UNGUARDED ``_mint_invitation``
impl, attributing ``issued_by`` to the existing ``tap_bootloader`` program actor for a
truthful audit trail — attribution, not authority: the bootloader does NOT (and must
not) hold ``auth.manage_users`` (req-tap-auth-passkey-genesis).

The minted invitation is an ``enroll_first`` grant of ``tap_admin``. The operator opens
the printed one-time link, registers a passkey, and is logged in as the admin. The
secret rides the URL *fragment* and is emitted to stdout only under ``--print-token``;
it is never accepted or echoed as an argv value (process listings are world-visible).

Example (fresh instance):
    manage.py migrate && manage.py sync_auth
    manage.py enroll_admin --email me@example.com --print-token
    # → open the printed http://<host>/auth/enroll/<public-id>#<secret> link
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from tap_auth.actors import BOOTLOADER, get_builtin_actor
from tap_auth.errors import MissingActor
from tap_auth.invitations import GENESIS_TTL, _mint_invitation
from tap_auth.models import InvitationAction, User, UserKind


class Command(BaseCommand):
    help = "Genesis: mint the first admin's passkey enrollment invitation (below the capability gate)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--email",
            required=True,
            metavar="EMAIL",
            help="Contact email recorded on the invitation (NOT identity — a label only).",
        )
        parser.add_argument(
            "--display-name",
            default="",
            metavar="NAME",
            help="Optional display name for the passkey / account.",
        )
        parser.add_argument(
            "--base-url",
            default="",
            metavar="URL",
            help="Origin for the enrollment link (default: TAP_PASSKEY_ORIGIN / TAP_BASE_URL).",
        )
        parser.add_argument(
            "--print-token",
            action="store_true",
            help="Emit the one-time enrollment link INCLUDING its secret fragment to stdout.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # Resolve the bootloader actor for the audit attribution. If it is absent, auth
        # sync has not run — refuse loudly rather than mint an unattributable invitation.
        try:
            bootloader = get_builtin_actor(BOOTLOADER)
        except MissingActor as exc:
            raise CommandError(
                "the tap_bootloader actor is missing — run `manage.py migrate` then "
                "`manage.py sync_auth` before genesis enrollment."
            ) from exc
        # The built-in bootloader IS a concrete User (AUTH_USER_MODEL) at runtime;
        # narrow the AbstractUser annotation so it types as the issued_by attribution.
        assert isinstance(bootloader, User)

        self._warn_if_admins_exist()

        invitation, secret = _mint_invitation(
            action=InvitationAction.ENROLL_FIRST,
            email=options["email"],
            display_name=options["display_name"],
            grants=["tap_admin"],
            issued_by=bootloader,
            ttl=GENESIS_TTL,
        )

        path = reverse("passkey_enroll", args=[invitation.public_id])
        base_url = (options["base_url"] or self._default_base_url()).rstrip("/")

        self.stdout.write(
            self.style.SUCCESS(
                f"Minted genesis admin invitation {invitation.public_id} "
                f"(expires {invitation.expires_at.isoformat()}, grants tap_admin)."
            )
        )
        if options["print_token"]:
            self.stdout.write("")
            self.stdout.write("One-time enrollment link (contains the secret — share over a secure channel):")
            self.stdout.write(f"  {base_url}{path}#{secret}")
        else:
            self.stdout.write(
                f"Public id: {invitation.public_id}. Re-run with --print-token to reveal the "
                "one-time enrollment link (the secret is shown once and never stored)."
            )

    def _default_base_url(self) -> str:
        origin = getattr(settings, "TAP_PASSKEY_ORIGIN", "") or getattr(settings, "TAP_BASE_URL", "")
        return origin or "http://localhost:8000"

    def _warn_if_admins_exist(self) -> None:
        """Genesis targets an empty instance; if a live admin already exists this is a
        deliberate additional-admin mint. Note it (not fatal — manage.py access is the
        root of trust) so an accidental re-run is visible."""
        from django.contrib.auth import get_user_model

        existing = (
            get_user_model()
            .objects.filter(
                is_active=True,
                deactivated_at__isnull=True,
                user_kind=UserKind.HUMAN,
                groups__name="tap_admin",
            )
            .count()
        )
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"Note: {existing} active human tap_admin already exist(s); minting an additional "
                    "admin enrollment invitation."
                )
            )
