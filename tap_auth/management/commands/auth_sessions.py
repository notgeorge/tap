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
    AmbiguousUserSelector,
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
        actor = self._resolve(options["as_user"], "--as-user")

        try:
            if options["all"]:
                count = invalidate_all_sessions(actor)
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) (global)."))
            elif options["user"]:
                target = self._resolve(options["user"], "--user")
                count = invalidate_user_sessions(actor, target)
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) for {options['user']}."))
            else:
                count = invalidate_session(actor, options["session_key"])
                self.stdout.write(self.style.SUCCESS(f"Invalidated {count} session(s) by key."))
        except AuthzError as exc:
            raise CommandError(f"Denied ({exc.reason}): {options['as_user']} lacks auth.manage_sessions.") from exc

    def _resolve(self, selector: str, flag: str) -> Any:
        """Resolve `selector` to a user, failing loud on not-found or on an
        ambiguous email (req-tap-auth-email-not-identity — never silently pick
        one; a wrong `--as-user`/`--user` is takeover/wrong-account DoS)."""
        try:
            user = resolve_user(selector)
        except AmbiguousUserSelector as exc:
            raise CommandError(f"{flag} {exc}") from exc
        if user is None:
            raise CommandError(f"{flag} '{selector}' not found (use a username or user id).")
        return user
