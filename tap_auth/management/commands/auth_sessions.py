"""`manage.py auth_sessions` — invalidate login sessions (req-tap-auth-sessions).

The auditable banhammer as a CLI: one of --all / --user / --session-key, acting
AS a named admin (--as-user) so the operation is attributable and
capability-gated (auth.manage_sessions) — never anonymous. This is a separate
lever from disabling login or deactivating a user; compose those explicitly.

Examples:
    manage.py auth_sessions --as-user alice --user bob          # ban bob's sessions
    manage.py auth_sessions --as-user alice --all               # mass logout
    manage.py auth_sessions --as-user alice --session-key abc123 # one session
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_auth.errors import AuthzError
from tap_auth.sessions import (
    invalidate_all_sessions,
    invalidate_session,
    invalidate_user_sessions,
    resolve_user,
)


class Command(BaseCommand):
    help = "Invalidate login sessions (global / per-user / per-session). Audited + capability-gated."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--as-user",
            required=True,
            metavar="USERNAME",
            help="The acting admin (must hold auth.manage_sessions). The operation is logged against them.",
        )
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--all", action="store_true", help="Invalidate EVERY active session (mass logout).")
        scope.add_argument("--user", metavar="USERNAME_OR_EMAIL", help="Invalidate all sessions of one user.")
        scope.add_argument("--session-key", metavar="KEY", help="Invalidate one session by key.")

    def handle(self, *args: Any, **options: Any) -> None:
        actor = resolve_user(options["as_user"])
        if actor is None:
            raise CommandError(f"--as-user '{options['as_user']}' not found (must be a real, authorized user).")

        try:
            if options["all"]:
                count = invalidate_all_sessions(actor)
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) (global)."))
            elif options["user"]:
                target = resolve_user(options["user"])
                if target is None:
                    raise CommandError(f"--user '{options['user']}' not found.")
                count = invalidate_user_sessions(actor, target)
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) for {options['user']}."))
            else:
                count = invalidate_session(actor, options["session_key"])
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) by key."))
        except AuthzError as exc:
            raise CommandError(f"Denied ({exc.reason}): {options['as_user']} lacks auth.manage_sessions.") from exc
