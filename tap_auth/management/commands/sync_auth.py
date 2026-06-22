"""`manage.py sync_auth` — explicit auth bootstrap (req-tap-auth-boot-6).

Hard-syncs TAP capabilities + projected permissions, the protected built-in
groups and their grants, and the protected program actors. Idempotent and
safe to re-run. This is the interim explicit command; the bootloader's `auth`
section handler will later run the same `sync_auth()` sequence within the boot
`auth` phase.

Capability removal is never implicit: pass each capability to be removed with
``--prune-capability NAME``; an undeclared DB capability absent from the registry
hard-fails rather than being silently kept or deleted.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_auth.sync import AuthSyncError, sync_auth

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Hard-sync TAP capabilities, protected groups, and built-in actors."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--prune-capability",
            action="append",
            default=[],
            dest="prune",
            metavar="NAME",
            help="Declare a capability expected to be removed (repeatable). "
            "Undeclared drift hard-fails; a stale declaration also hard-fails.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        prune = tuple(options["prune"])
        try:
            sync_auth(declared_prune=prune)
        except AuthSyncError as exc:
            logger.error("[5dd4] auth sync failed: %s", exc)
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("auth sync complete"))
