"""`manage.py boot` — the canonical TAP standup (req-boot-app).

One explicit command stands a fresh, migrated database up to a populated, usable
instance by applying a boot profile in fixed phases (auth → population). It is the
same path in dev (`spawn-session.sh`, req-boot-spawn-bridge) and in a customer
deployment — dog-fooded continuously before any customer relies on it.

Profile resolution: ``--profile`` > ``$TAP_BOOT_PROFILE``.
- dev / manual (default): no profile ⇒ a clean auth-only standup that reaches out
  to nothing (req-boot-profile-4).
- deploy / entrypoint (``--require-profile``): a missing profile fails loud unless
  ``--allow-empty`` is given — a deployment must never silently start empty
  (req-boot-profile-5).

Boot is zero-touch: no prompts, ever (req-boot-trust). Migrations are a precondition
(run by the container entrypoint), not a boot phase.

Spec: specs/spec-tap-boot-v0.md.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_boot.orchestrator import BootError, run_boot
from tap_boot.profile import BootProfileError, load_profile, profile_ids

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600


class Command(BaseCommand):
    help = "Stand a TAP instance up from a boot profile (auth → population). See specs/spec-tap-boot-v0.md."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--profile",
            default=None,
            help="Profile id (basename of boot/<id>.json). Overrides $TAP_BOOT_PROFILE.",
        )
        parser.add_argument(
            "--require-profile",
            action="store_true",
            default=False,
            help="Deploy mode: a missing profile fails loud unless --allow-empty (req-boot-profile-5).",
        )
        parser.add_argument(
            "--allow-empty",
            action="store_true",
            default=False,
            help="Permit an empty (auth-only) standup under --require-profile.",
        )
        parser.add_argument(
            "--list",
            dest="list_profiles",
            action="store_true",
            default=False,
            help="List available profiles (id + description) and exit.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=_DEFAULT_TIMEOUT_SECONDS,
            help=f"Seconds to await each fire-collector step's terminal state (default {_DEFAULT_TIMEOUT_SECONDS}).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list_profiles"]:
            self._list_profiles()
            return

        profile_id = (options["profile"] or os.environ.get("TAP_BOOT_PROFILE") or "").strip()

        profile = None
        if profile_id:
            try:
                profile = load_profile(profile_id)
            except BootProfileError as exc:
                logger.error("[f750] boot profile load failed: %s", exc)
                raise CommandError(str(exc)) from exc
        elif options["require_profile"] and not options["allow_empty"]:
            raise CommandError(
                "Deploy boot requires an explicit profile (--profile / $TAP_BOOT_PROFILE) or --allow-empty; "
                "refusing to start empty-but-apparently-healthy (req-boot-profile-5)."
            )

        try:
            run_boot(profile, timeout_seconds=float(options["timeout"]), echo=self.stdout.write)
        except BootError as exc:
            logger.error("[916b] boot failed: %s", exc)
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("boot complete"))

    def _list_profiles(self) -> None:
        ids = profile_ids()
        if not ids:
            self.stdout.write("No boot profiles found.")
            return
        self.stdout.write("Boot profiles:")
        for pid in ids:
            try:
                desc = load_profile(pid).description
            except BootProfileError:
                desc = "(unreadable / invalid)"
            self.stdout.write(f"  {pid} — {desc}" if desc else f"  {pid}")
