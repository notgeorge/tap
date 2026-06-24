"""`manage.py boot` — the canonical TAP standup (req-boot-app).

One explicit command stands a fresh, migrated database up to a populated, usable
instance by applying a boot profile in fixed phases (auth → population). It is the
same path in dev (`spawn-session.sh`, req-boot-spawn-bridge) and in a customer
deployment — dog-fooded continuously before any customer relies on it.

Profile resolution: ``--profile`` > ``$TAP_BOOT_PROFILE``. A profile is **required
by default** — a missing one fails loud, so a deployment never silently starts
empty (req-boot-profile-5). The single escape hatch is ``--allow-empty``, an
explicit opt-in to an auth-only, no-outbound standup (req-boot-profile-4).

Boot is zero-touch: no prompts, ever (req-boot-trust). Migrations are a precondition
(run by the container entrypoint), not a boot phase. Per-collector await timeouts
are declared on each fire-collector step (default 90s).

Spec: specs/spec-tap-boot-v0.md.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from tap_auth.sync import AuthSyncError
from tap_boot.orchestrator import BootError, run_boot
from tap_boot.profile import BootProfileError, load_profile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Stand a TAP instance up from a boot profile (auth → population). See specs/spec-tap-boot-v0.md."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--profile",
            default=None,
            help="Profile id (basename of boot/<id>.json). Overrides $TAP_BOOT_PROFILE.",
        )
        parser.add_argument(
            "--allow-empty",
            action="store_true",
            default=False,
            help="Permit an auth-only standup with no profile (req-boot-profile-4). "
            "Without it, a missing profile fails loud (req-boot-profile-5).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        profile_id = (options["profile"] or os.environ.get("TAP_BOOT_PROFILE") or "").strip()

        profile = None
        if profile_id:
            try:
                profile = load_profile(profile_id)
            except BootProfileError as exc:
                logger.error("[f750] boot profile load failed: %s", exc)
                raise CommandError(str(exc)) from exc
        elif not options["allow_empty"]:
            raise CommandError(
                "A boot profile is required: pass --profile <id> or set $TAP_BOOT_PROFILE. "
                "To stand up auth-only with no profile on purpose, pass --allow-empty "
                "(refusing to start empty-but-apparently-healthy by default — req-boot-profile-5)."
            )

        try:
            run_boot(profile, echo=self.stdout.write)
        except (BootError, AuthSyncError) as exc:
            logger.error("[916b] boot failed: %s", exc)
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("boot complete"))
