"""`manage.py export_dev_passkey` — export the dev admin's PUBLIC passkey record once.

The "register once" half of dev bootstrap replay (req-tap-auth-passkey-dev-bootstrap): a
developer registers a `localhost` passkey against one session, then runs this to emit the
PUBLIC credential record. Committing that record to the operator's 0600 secrets dir lets
every freshly-spawned session bind the same passkey with no re-registration
(``enroll_admin --import-dev-passkey``).

Prefer `manage.py bootstrap_dev_passkey`, which drives register → wait → emit as one guided
step and never leaves the operator holding a half-finished flow. This command remains the
low-level "emit the record for an already-registered passkey" primitive it always was.

The record is written to STDOUT, not to a file — the secrets mount is read-only in the
container, and the operator (not this process) owns where it lands (req-…-dev-bootstrap-12).
The record carries ONLY public material (never the private key); its confidentiality is
low-stakes, its INTEGRITY is what matters (a self-digest is stamped, and the file's 0600
operator-owned home is the named load-bearing mitigation). Redirect stdout to the record
path, writing atomically so a failed run cannot leave a truncated record behind:

    manage.py export_dev_passkey > admin.dev-passkey.json.tmp \
      && mv admin.dev-passkey.json.tmp ~/tap-secrets/dev-passkey/admin.dev-passkey.json
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_auth.passkey.dev_record import DEV_ADMIN_USERNAME, DevRecordError, build_record_for_user


class Command(BaseCommand):
    help = "Export the dev admin's PUBLIC passkey record (register-once → replay) to stdout."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--username",
            default=DEV_ADMIN_USERNAME,
            metavar="NAME",
            help=(
                f"The user whose passkey to export (default: {DEV_ADMIN_USERNAME} — the account "
                "`--import-dev-passkey` replays onto, so the default round-trips)."
            ),
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
            record = build_record_for_user(username, credential_id=options["credential_id"])
        except DevRecordError as exc:
            raise CommandError(str(exc)) from exc

        # The record IS the machine payload — write ONLY the JSON to stdout so a redirect
        # captures a clean file. Human context goes to stderr (req-…-dev-bootstrap-11).
        self.stderr.write(self.style.SUCCESS(f"Exporting passkey record for '{username}'."))
        self.stdout.write(json.dumps(record, indent=2, sort_keys=True))
