"""`manage.py export_dev_passkey` — export the dev admin's PUBLIC passkey record once.

The "register once" half of dev bootstrap replay (req-tap-auth-passkey-dev-bootstrap): a
developer registers a `localhost` passkey against one session, then runs this to emit the
PUBLIC credential record. Committing that record to the operator's 0600 secrets dir lets
every freshly-spawned session bind the same passkey with no re-registration
(``enroll_admin --import-dev-passkey``).

The record is written to STDOUT, not to a file — the secrets mount is read-only in the
container, and the operator (not this process) owns where it lands. The record carries ONLY
public material (never the private key); its confidentiality is low-stakes, its INTEGRITY is
what matters (a self-digest is stamped, and the file's 0600 operator-owned home is the named
load-bearing mitigation). Redirect stdout to the record path:

    manage.py export_dev_passkey > ~/tap-secrets/dev-passkey/admin.dev-passkey.json
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_auth.models import User, WebAuthnCredential
from tap_auth.passkey.dev_record import DEV_ADMIN_USERNAME, build_dev_record


class Command(BaseCommand):
    help = "Export the dev admin's PUBLIC passkey record (register-once → replay) to stdout."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--username",
            default=DEV_ADMIN_USERNAME,
            metavar="NAME",
            help=f"The user whose passkey to export (default: {DEV_ADMIN_USERNAME}).",
        )
        parser.add_argument(
            "--credential-id",
            default="",
            metavar="ID",
            help="Export this specific credential id (base64url). Default: the user's sole/most-recent credential.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"no user '{username}' — register a passkey against a running session first, " "then export it."
            ) from exc

        handle = getattr(user, "webauthn_handle", None)
        if handle is None:
            raise CommandError(
                f"user '{username}' has no WebAuthn user handle — has this account ever registered a passkey?"
            )

        credential = self._select_credential(user, options["credential_id"])
        record = build_dev_record(user_handle_hex=handle.handle, credential=credential)

        # The record IS the machine payload — write ONLY the JSON to stdout so a redirect
        # captures a clean file. Human context goes to stderr.
        self.stderr.write(
            self.style.SUCCESS(
                f"Exporting passkey {credential.redacted_credential_id} for '{username}'. "
                "Redirect stdout into your 0600 secrets dir."
            )
        )
        self.stdout.write(json.dumps(record, indent=2, sort_keys=True))

    def _select_credential(self, user: User, credential_id: str) -> WebAuthnCredential:
        """The credential to export: the named one, or (when unspecified) the user's only
        credential. Refuse to guess when a user has several and none is named — export is a
        deliberate act, and silently picking one could replay the wrong key."""
        credentials = WebAuthnCredential.objects.filter(user=user)
        if credential_id:
            try:
                return credentials.get(credential_id=credential_id)
            except WebAuthnCredential.DoesNotExist as exc:
                raise CommandError(f"user '{user.username}' has no credential '{credential_id}'.") from exc

        found = list(credentials.order_by("-created")[:2])
        if not found:
            raise CommandError(f"user '{user.username}' has no registered passkey to export.")
        if len(found) > 1:
            raise CommandError(
                f"user '{user.username}' has multiple passkeys — pass --credential-id to choose which to export."
            )
        return found[0]
