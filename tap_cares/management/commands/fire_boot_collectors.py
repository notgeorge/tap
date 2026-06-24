"""Fire a boot profile's collectors so a freshly-spawned stack comes up populated.

A dev/debug bootstrap — NOT the production scheduler. Reads a boot profile from
the top-level ``boot/`` directory and fires each enabled collector, in declared
order, via ``tap_cares.services.run_collection``, awaiting each collector's
``CollectionJob`` to a terminal state before firing the next. Sequential
await-to-terminal is required for correctness: later collectors may depend on
grid state written by earlier ones (e.g. the samsite compliance collector reads
``aws_account`` nodes the boto3 collector lands).

The real app runs collectors asynchronously on the Steady Queue backend (a
worker drains jobs out-of-process), so ``run_collection`` only *enqueues* — this
command polls ``CollectionJob.status`` to terminal rather than reading an inline
result.

Profile selection (first hit wins): ``--profile`` → ``$TAP_BOOT_PROFILE`` →
nothing. With no profile selected the command is a clean no-op (exit 0) — boot
collection is never implicit.

Spec: specs/spec-dev-boot-collectors.md.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import jsonschema
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tap_auth.actors import BOOTLOADER, acting_as, get_builtin_actor

# tap_cares/management/commands/fire_boot_collectors.py -> tap_cares/schemas/...
_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "boot-profile.schema.json"

_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_TIMEOUT_SECONDS = 600


def _boot_dir() -> Path:
    """Top-level ``boot/`` directory holding profile data files."""
    return Path(settings.BASE_DIR) / "boot"


class Command(BaseCommand):
    help = "Fire a boot profile's collectors (dev bootstrap). See specs/spec-dev-boot-collectors.md."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            default=None,
            help="Profile id (basename of boot/<id>.json). Overrides $TAP_BOOT_PROFILE.",
        )
        parser.add_argument(
            "--list",
            dest="list_profiles",
            action="store_true",
            default=False,
            help="List available profiles (id + description) and exit without firing.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=_DEFAULT_TIMEOUT_SECONDS,
            help=f"Seconds to await each collector's terminal state (default {_DEFAULT_TIMEOUT_SECONDS}).",
        )

    def handle(self, *args, **options):
        if options["list_profiles"]:
            self._list_profiles()
            return

        # Profile resolution: --profile > $TAP_BOOT_PROFILE > none (no-op).
        profile = (options["profile"] or os.environ.get("TAP_BOOT_PROFILE") or "").strip()
        if not profile:
            self.stdout.write("No boot profile selected (--profile / $TAP_BOOT_PROFILE unset); nothing to fire.")
            return

        data = self._load_profile(profile)
        on_failure: str = data["on_failure"]
        timeout: int = options["timeout"]

        # Pre-resolve every enabled collector so an unknown key aborts the run
        # before any collector fires (req-dev-boot-collectors-profiles-4).
        from tap_cares.models import Collector

        plan: list[tuple[dict[str, Any], Collector]] = []
        for entry in data["collectors"]:
            if not entry.get("enabled", False):
                self.stdout.write(f"  [skip] {entry['key']} (disabled)")
                continue
            try:
                collector = Collector.objects.get(collector_registry=entry["key"])
            except Collector.DoesNotExist:
                raise CommandError(
                    f"Unknown collector key '{entry['key']}' — not registered. " "Aborting before any collector fires."
                ) from None
            plan.append((entry, collector))

        if not plan:
            self.stdout.write(f"Profile '{profile}': no enabled collectors; nothing to fire.")
            return

        self.stdout.write(
            self.style.WARNING(f"Firing boot profile '{profile}' — {len(plan)} collector(s), on_failure={on_failure}.")
        )

        # Boot fires collectors as the named tap_bootloader program actor: a CLI
        # boot process has no request middleware to bind one, and run_collection's
        # trigger gate (cares.run_collectors) requires a named triggering actor.
        # tap_bootloader holds cares.run_collectors; the runs themselves still
        # execute as tap_cares.collector (run_collection's internal swap).
        failures: list[str] = []
        with acting_as(get_builtin_actor(BOOTLOADER)):
            for index, (entry, collector) in enumerate(plan):
                if self._fire_one(collector, entry, timeout):
                    continue
                failures.append(entry["key"])
                if on_failure == "abort":
                    remaining = len(plan) - index - 1
                    raise CommandError(
                        f"Collector '{entry['key']}' did not succeed; on_failure=abort — stopping. "
                        f"{remaining} collector(s) not run."
                    )

        if failures:
            raise CommandError(
                f"Boot profile '{profile}' completed with {len(failures)} failed collector(s): "
                f"{', '.join(failures)}."
            )
        self.stdout.write(
            self.style.SUCCESS(f"Boot profile '{profile}' complete — {len(plan)} collector(s) successful.")
        )

    def _fire_one(self, collector, entry: dict[str, Any], timeout: int) -> bool:
        """Fire one collector and await its job to terminal. True iff SUCCESSFUL."""
        from tap_cares.models import CollectionJobStatus
        from tap_cares.services import run_collection

        run_mode = entry.get("run_mode", "full")
        self.stdout.write(f"  [fire] {entry['key']} (run_mode={run_mode}) ...")

        job = run_collection(
            collector,
            manual_run=True,
            manual_run_source="fire_boot_collectors",
            run_mode=run_mode,
        )

        # A real Steady Queue worker drains the job out-of-process; poll to terminal.
        deadline = time.monotonic() + timeout
        while True:
            job.refresh_from_db()
            if job.status in (CollectionJobStatus.SUCCESSFUL.value, CollectionJobStatus.FAILED.value):
                break
            if time.monotonic() >= deadline:
                self.stderr.write(self.style.ERROR(f"    TIMEOUT after {timeout}s — job still {job.status}."))
                return False
            time.sleep(_POLL_INTERVAL_SECONDS)

        if job.status == CollectionJobStatus.SUCCESSFUL.value:
            self.stdout.write(self.style.SUCCESS(f"    OK — {collector.name}: {job.summary or 'successful'}"))
            return True
        self.stderr.write(self.style.ERROR(f"    FAILED — {collector.name}: {job.summary or 'see CollectionJob'}"))
        return False

    def _load_profile(self, profile: str) -> dict[str, Any]:
        path = _boot_dir() / f"{profile}.json"
        if not path.is_file():
            available = ", ".join(self._profile_ids()) or "(none)"
            raise CommandError(f"Boot profile '{profile}' not found at {path}. Available: {available}.")
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read boot profile '{profile}': {exc}") from exc
        try:
            schema = json.loads(_SCHEMA_PATH.read_text())
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            raise CommandError(f"Boot profile '{profile}' failed schema validation: {exc.message}") from exc
        return data

    def _profile_ids(self) -> list[str]:
        boot_dir = _boot_dir()
        if not boot_dir.is_dir():
            return []
        return sorted(p.stem for p in boot_dir.glob("*.json"))

    def _list_profiles(self) -> None:
        ids = self._profile_ids()
        if not ids:
            self.stdout.write(f"No boot profiles found in {_boot_dir()}.")
            return
        self.stdout.write(f"Boot profiles in {_boot_dir()}:")
        for pid in ids:
            try:
                desc = json.loads((_boot_dir() / f"{pid}.json").read_text()).get("description", "")
            except OSError, json.JSONDecodeError:
                desc = "(unreadable)"
            self.stdout.write(f"  {pid} — {desc}" if desc else f"  {pid}")
